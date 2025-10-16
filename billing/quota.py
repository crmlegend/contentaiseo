# billing/quota.py
from django.core.cache import cache
from django.utils import timezone
from django.db import transaction
from .models import ApiKey

STATE_TTL   = 600    # 10 minutes
FLUSH_EVERY = 10     # update DB every 10 trial requests (small since quota=10)

def _state_key(h): return f"auth:state:{h}"
def _count_key(h): return f"auth:count:{h}"

def _load_state_from_db(key_hash: str):
    ak = (ApiKey.objects
          .select_related("user")
          .only("plan","status","revoked_at","trial_quota","used_requests","last_used_at","user__is_active")
          .filter(key_hash=key_hash)
          .first())
    if not ak or not ak.user or not ak.user.is_active or not ak.is_active:
        return {"status": "none", "trial_quota": 0}
    if ak.plan == "trial":
        return {"status": "trial", "trial_quota": int(ak.trial_quota or 0)}
    return {"status": "subscribed", "trial_quota": None}

def get_state(key_hash: str):
    sk = _state_key(key_hash)
    state = cache.get(sk)
    if state:
        return state
    state = _load_state_from_db(key_hash)
    cache.set(sk, state, STATE_TTL)
    return state

def invalidate_state(key_hash: str):
    cache.delete(_state_key(key_hash))

def try_consume_trial(key_hash: str, hard_quota: int) -> tuple[bool, int]:
    """
    Returns (allowed, used_now). Uses Redis INCR if available; else DB row lock.
    """
    if hard_quota <= 0:
        return (False, 0)

    # Fast path: Redis counter
    try:
        used = cache.incr(_count_key(key_hash))
        cache.touch(_count_key(key_hash), 30*24*3600)
        if used <= hard_quota:
            if used % FLUSH_EVERY == 0:
                ApiKey.objects.filter(key_hash=key_hash, status="active").update(
                    used_requests=used, last_used_at=timezone.now()
                )
            return (True, used)
        # Exceeded → revoke in DB and invalidate cache
        ApiKey.objects.filter(key_hash=key_hash).update(
            status="revoked", revoked_at=timezone.now(), used_requests=used
        )
        invalidate_state(key_hash)
        return (False, used)
    except Exception:
        # Fallback if cache not configured: serialize on DB
        with transaction.atomic():
            ak = ApiKey.objects.select_for_update().filter(key_hash=key_hash, status="active").first()
            if not ak or ak.plan != "trial":
                return (False, 0)
            if ak.used_requests >= hard_quota:
                ak.status = "revoked"
                ak.revoked_at = timezone.now()
                ak.save(update_fields=["status","revoked_at"])
                invalidate_state(key_hash)
                return (False, ak.used_requests)
            ak.used_requests += 1
            ak.last_used_at  = timezone.now()
            ak.save(update_fields=["used_requests","last_used_at"])
            return (True, ak.used_requests)
