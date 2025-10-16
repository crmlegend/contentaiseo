from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from .utils import verify_token_in_db
from .models import ApiKey

STATE_TTL   = 600
FLUSH_EVERY = 10
PAID_PLANS  = {"pro", "business", "enterprise"}  # <-- add more plan names here as needed

def _state_key(key_hash: str) -> str:
    return f"auth:state:{key_hash}"

def _count_key(key_hash: str) -> str:
    return f"auth:count:{key_hash}"

def _load_state_from_row(row: ApiKey) -> dict:
    if not row or not row.is_active:
        return {"status": "none", "trial_quota": 0}
    if row.plan == "trial":
        return {"status": "trial", "trial_quota": int(row.trial_quota or 0)}
    return {"status": "subscribed", "trial_quota": None}

def _get_state(row: ApiKey) -> dict:
    if not getattr(row, "key_hash", None):
        return _load_state_from_row(row)
    sk = _state_key(row.key_hash)
    state = cache.get(sk)
    if state:
        return state
    state = _load_state_from_row(row)
    cache.set(sk, state, STATE_TTL)
    return state

def _invalidate_state(row: ApiKey):
    if getattr(row, "key_hash", None):
        cache.delete(_state_key(row.key_hash))

class ApiKeyAuthentication(BaseAuthentication):
    def authenticate(self, request):
        if not request.path.startswith("/v1/"):
            return None

        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            raise AuthenticationFailed("Missing or invalid Authorization header")

        token = auth.split(" ", 1)[1].strip()

        row = verify_token_in_db(token)

        test_key = getattr(settings, "TEST_KEY", None)
        if not row and token == test_key:
            return (None, {"tenant_id": "dev", "plan": "demo"})

        if not row:
            raise AuthenticationFailed("Invalid API key")

        if not row.is_active:
            raise AuthenticationFailed("Key revoked")

        # Paid? allow immediately.
        if row.plan and (row.plan in PAID_PLANS or row.plan != "trial"):
            return (None, {"tenant_id": row.tenant_id, "plan": row.plan})

        # Trial: enforce quota
        state = _get_state(row)

        # Optional: hygiene if cache stale while DB says paid
        if row.plan != "trial" and state.get("status") != "subscribed":
            _invalidate_state(row)
            return (None, {"tenant_id": row.tenant_id, "plan": row.plan})

        if state["status"] != "trial":
            raise AuthenticationFailed("Access denied")

        quota = int(state["trial_quota"] or 0)
        if quota <= 0:
            raise AuthenticationFailed("Trial quota exhausted")

        # Fast path via cache/Redis
        used_now = None
        try:
            ck = _count_key(row.key_hash)
            used_now = cache.incr(ck)
            cache.touch(ck, 30 * 24 * 3600)
        except Exception:
            used_now = None

        if used_now is not None:
            if used_now <= quota:
                if used_now % FLUSH_EVERY == 0:
                    ApiKey.objects.filter(pk=row.pk, status="active").update(
                        used_requests=used_now, last_used_at=timezone.now()
                    )
                return (None, {"tenant_id": row.tenant_id, "plan": "trial", "used": used_now, "quota": quota})

            ApiKey.objects.filter(pk=row.pk).update(
                status="revoked", revoked_at=timezone.now(), used_requests=used_now
            )
            _invalidate_state(row)
            raise AuthenticationFailed("Trial quota exhausted")

        # DB fallback with row lock
        updated = ApiKey.objects.select_for_update().filter(pk=row.pk, status="active").first()
        if not updated or updated.plan != "trial":
            raise AuthenticationFailed("Access denied")

        if updated.used_requests >= quota:
            updated.status = "revoked"
            updated.revoked_at = timezone.now()
            updated.save(update_fields=["status", "revoked_at"])
            _invalidate_state(updated)
            raise AuthenticationFailed("Trial quota exhausted")

        updated.used_requests += 1
        updated.last_used_at = timezone.now()
        updated.save(update_fields=["used_requests", "last_used_at"])

        return (None, {"tenant_id": updated.tenant_id, "plan": "trial", "used": updated.used_requests, "quota": quota})
