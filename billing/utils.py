# billing/utils.py
import secrets
import hashlib
from typing import Optional
from django.utils import timezone
from django.contrib.auth import get_user_model
from .models import ApiKey

User = get_user_model()

# Visible prefix in the raw token (keep your current choice)
TOKEN_PREFIX_STR = "cg_live_"
# Must be <= models.ApiKey.key_prefix max_length
PREFIX_LEN = 16

TRIAL_DEFAULT_QUOTA = 10  # <-- free tries for new users


# ----------------------------
# Helpers
# ----------------------------
def _sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def make_api_key():
    """
    Generates a raw API key:
      plain:  full token (prefix + random)
      prefix: stored & shown (safe)
      suffix: stored (plaintext in your current design)
    """
    plain = TOKEN_PREFIX_STR + secrets.token_urlsafe(36)
    prefix = plain[:PREFIX_LEN]
    suffix = plain[PREFIX_LEN:]
    return plain, prefix, suffix


def _persist_key(
    *,
    user: Optional[User],
    plan: str,
    tenant_id: Optional[str],
    customer_id: Optional[str],
    prefix: str,
    suffix: str,
    trial_quota: Optional[int] = None,
) -> ApiKey:
    """
    Create the ApiKey row. We also compute and store key_hash so the auth layer
    can use cache/Redis with a stable key.
    """
    plain = f"{prefix}{suffix}"
    # choose a stable tenant id even if user is None (e.g., webhook path)
    _tenant = str(tenant_id or (getattr(user, "id", None) or customer_id or "anon"))

    row = ApiKey.objects.create(
        user=user,
        key_prefix=prefix,
        plain_suffix=suffix,               # (you keep plaintext suffix today)
        key_hash=_sha256_hex(plain),       # store hash for fast lookups/caching
        tenant_id=_tenant,
        plan=plan,
        status="active",
        customer_id=customer_id or (getattr(user, "stripe_customer_id", None) or None),
        trial_quota=trial_quota,
        used_requests=0,
        last_used_at=None,
    )
    return row


def verify_token_in_db(token: str) -> Optional[ApiKey]:
    """
    Verify incoming raw token when DB stores prefix + plaintext suffix.
    Returns the ApiKey row if valid & active, else None.

    NOTE: We also backfill row.key_hash if missing to support the fast cache path.
    """
    if not token:
        return None
    token = token.strip()
    if len(token) < PREFIX_LEN:
        return None

    prefix = token[:PREFIX_LEN]

    qs = (
        ApiKey.objects
        .filter(key_prefix=prefix, status="active", revoked_at__isnull=True)
        .order_by("-created_at")
    )

    for row in qs:
        expected = (row.key_prefix or "") + (row.plain_suffix or "")
        if token == expected:
            # Backfill key_hash if empty (older rows)
            if not getattr(row, "key_hash", None):
                row.key_hash = _sha256_hex(token)
                row.save(update_fields=["key_hash"])
            return row
    return None


def revoke_all_keys(user: User):
    """Revoke all active keys for a user."""
    ApiKey.objects.filter(
        user=user, status="active", revoked_at__isnull=True
    ).update(status="revoked", revoked_at=timezone.now())


def revoke_all_keys_by_customer(customer_id: str):
    """Revoke all active keys for a given Stripe customer id."""
    if not customer_id:
        return
    ApiKey.objects.filter(
        customer_id=customer_id, status="active", revoked_at__isnull=True
    ).update(status="revoked", revoked_at=timezone.now())


# ----------------------------
# Issuers (trial & paid)
# ----------------------------
def issue_trial_key_for_user(*, user: User, tenant_id=None, quota: int = TRIAL_DEFAULT_QUOTA) -> str:
    """
    Issue a TRIAL key with a request quota (default 10).
    Returns the RAW token (show to the user once).
    """
    plain, prefix, suffix = make_api_key()
    _persist_key(
        user=user,
        plan="trial",
        tenant_id=tenant_id,
        customer_id=None,
        prefix=prefix,
        suffix=suffix,
        trial_quota=int(quota or TRIAL_DEFAULT_QUOTA),
    )
    return plain


def issue_api_key_for_user(*, user: User, plan="pro", tenant_id=None, customer_id=None) -> str:
    """
    Rotate to a PAID key (pro). Revokes any previously active keys for cleanliness.
    Returns the RAW token (show to the user once).
    """
    ApiKey.objects.filter(
        user=user, status="active", revoked_at__isnull=True
    ).update(status="revoked", revoked_at=timezone.now())

    plain, prefix, suffix = make_api_key()
    _persist_key(
        user=user,
        plan=plan,
        tenant_id=tenant_id,
        customer_id=customer_id,
        prefix=prefix,
        suffix=suffix,
        trial_quota=None,  # paid keys don't use request quota
    )
    return plain


# ----------------------------
# Plan transitions
# ----------------------------
def activate_paid_plan_for_user(
    *,
    user: User,
    customer_id: Optional[str] = None,
    rotate_key: bool = True
) -> Optional[str]:
    """
    When a user subscribes:
      - If rotate_key=True (recommended), revoke old keys and issue a new pro key.
      - If rotate_key=False, flip existing active keys to pro (no new token).
    Returns new raw token if rotated, else None.
    """
    if rotate_key:
        return issue_api_key_for_user(
            user=user, plan="pro", tenant_id=user.id, customer_id=customer_id
        )

    # Flip existing active keys to pro (keeps the same token)
    ApiKey.objects.filter(user=user, status="active", revoked_at__isnull=True).update(
        plan="pro",
        customer_id=customer_id or "",
        trial_quota=None,
    )
    return None


def activate_paid_plan_for_customer(
    *,
    customer_id: str,
    rotate_key: bool = True
) -> Optional[str]:
    """
    Same as activate_paid_plan_for_user, but when the webhook only has customer_id.
    Tries to resolve the user; if none is found, still rotates keys by customer_id.
    """
    if not customer_id:
        return None

    user = User.objects.filter(stripe_customer_id=customer_id).first()

    if user:
        return activate_paid_plan_for_user(user=user, customer_id=customer_id, rotate_key=rotate_key)

    # No user row mapped (edge cases) — still ensure active keys for this customer flip to pro
    if rotate_key:
        revoke_all_keys_by_customer(customer_id)
        # Issue a paid key not tied to a user (rare; keeps calls working if you use customer-only auth)
        plain, prefix, suffix = make_api_key()
        _persist_key(
            user=None,
            plan="pro",
            tenant_id=customer_id,   # fallback tenant = customer id
            customer_id=customer_id,
            prefix=prefix,
            suffix=suffix,
            trial_quota=None,
        )
        return plain

    # Flip existing keys to pro without rotating
    ApiKey.objects.filter(customer_id=customer_id, status="active", revoked_at__isnull=True).update(
        plan="pro",
        trial_quota=None,
    )
    return None
