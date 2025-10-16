# from django.db import models
# from django.conf import settings
# from django.utils import timezone


# class ApiKey(models.Model):
#     """
#     Single source of truth for user API keys.
#     Store only a hash of the full key. Show key_prefix on UI.
#     Older keys are 'revoked' instead of hard-deleted to enable rotation.
#     """

#     user = models.ForeignKey(
#         settings.AUTH_USER_MODEL,
#         null=True, blank=True,
#         on_delete=models.SET_NULL,
#         related_name="api_keys",
#     )

#     # What you can safely display
#     key_prefix = models.CharField(max_length=16, db_index=True)

#     # Never store the raw key — only a hash
#     key_hash = models.CharField(max_length=255)

#     # Optional bookkeeping
#     tenant_id = models.CharField(max_length=128)
#     plan = models.CharField(max_length=16, default="demo")

#     # Lifecycle
#     status = models.CharField(max_length=16, default="active")  # active | revoked
#     created_at = models.DateTimeField(auto_now_add=True)
#     revoked_at = models.DateTimeField(null=True, blank=True)

#     # Stripe link (helps webhooks look up user)
#     customer_id = models.CharField(max_length=128, null=True, blank=True)
#     plain_suffix = models.TextField(null=True, blank=True)

#     class Meta:
#         ordering = ["-created_at"]
#         indexes = [
#             models.Index(fields=["user", "status"]),
#             models.Index(fields=["customer_id"]),
#             models.Index(fields=["key_prefix"]),
#         ]

#     def __str__(self):
#         return f"{self.key_prefix} ({self.plan}/{self.status})"

#     @property
#     def is_active(self) -> bool:
#         return self.status == "active" and self.revoked_at is None

#     def revoke(self, when: timezone.datetime | None = None, save=True):
#         self.status = "revoked"
#         self.revoked_at = when or timezone.now()
#         if save:
#             self.save(update_fields=["status", "revoked_at"])


# class WebhookEvent(models.Model):
#     event_id = models.CharField(max_length=255, unique=True)
#     kind = models.CharField(max_length=64)
#     received_at = models.DateTimeField(auto_now_add=True)

#     def __str__(self):
#         return f"{self.kind}:{self.event_id}"









from django.db import models
from django.conf import settings
from django.utils import timezone
from django.db.models import F


class ApiKey(models.Model):
    """
    Single source of truth for user API keys.

    - Display only key_prefix; never expose full raw keys.
    - key_hash is a hash of the full key (prefix + suffix) for fast lookups/caching.
    - Trial keys use a request quota (trial_quota / used_requests).
    - Paid keys bypass trial limits.
    """

    PLAN_CHOICES = (
<<<<<<< HEAD
        ("trial", "trial"),     # free tries (request-based)
        ("pro", "pro"),         # example paid plan
        ("demo", "demo"),       # keep your existing default if you use it
=======
        ("trial", "trial"),   # free tries (request-based)
        ("pro", "pro"),       # example paid plan
        ("demo", "demo"),     # optional placeholder
>>>>>>> 610509e17015e87ecbab03f162f85fcbe64e03f2
    )
    STATUS_CHOICES = (
        ("active", "active"),
        ("revoked", "revoked"),
    )

<<<<<<< HEAD
=======
    # Ownership
>>>>>>> 610509e17015e87ecbab03f162f85fcbe64e03f2
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="api_keys",
    )

    # Safe-to-display portion of the key
    key_prefix = models.CharField(max_length=16, db_index=True)

<<<<<<< HEAD
    # Never store the raw key — only a hash (make it unique + indexed for O(1) lookups)
=======
    # Hash of the full key (prefix+suffix), unique for O(1) lookups
>>>>>>> 610509e17015e87ecbab03f162f85fcbe64e03f2
    key_hash = models.CharField(max_length=255, unique=True, db_index=True)

    # Optional tenancy/bookkeeping
    tenant_id = models.CharField(max_length=128)

    # Plan & lifecycle
    plan = models.CharField(max_length=16, choices=PLAN_CHOICES, default="demo")
<<<<<<< HEAD
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="active")  # active | revoked
=======
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="active")
>>>>>>> 610509e17015e87ecbab03f162f85fcbe64e03f2
    created_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    # Payment linkage (e.g., Stripe)
    customer_id = models.CharField(max_length=128, null=True, blank=True)

<<<<<<< HEAD
    # (Legacy helper your code already had; safe to keep for now)
    plain_suffix = models.TextField(null=True, blank=True)

    # -------- NEW: request-based trial fields --------
    # e.g., 10 for new users; NULL for paid keys (no request limit)
    trial_quota = models.PositiveIntegerField(null=True, blank=True)
    # persisted snapshot for analytics / after restarts
    used_requests = models.PositiveIntegerField(default=0)
    # last time this key was used (optional, nice in admin)
    last_used_at = models.DateTimeField(null=True, blank=True)
    # -------------------------------------------------
=======
    # Legacy helper (you currently store plaintext suffix alongside prefix)
    plain_suffix = models.TextField(null=True, blank=True)

    # ---------- Request-based trial fields --------------
    # e.g., 10 for trials; NULL for paid keys (no request limit)
    trial_quota = models.PositiveIntegerField(null=True, blank=True)
    # persisted count (for admin/analytics & fallback when cache is down)
    used_requests = models.PositiveIntegerField(default=0)
    # last time this key was used
    last_used_at = models.DateTimeField(null=True, blank=True)
    # ------------------------------------------------

>>>>>>> 610509e17015e87ecbab03f162f85fcbe64e03f2

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["customer_id"]),
            models.Index(fields=["key_prefix"]),
<<<<<<< HEAD
            # key_hash already unique+indexed via field args, so no extra index needed here
=======
            # key_hash already unique+indexed via field args
>>>>>>> 610509e17015e87ecbab03f162f85fcbe64e03f2
        ]

    def __str__(self):
        return f"{self.key_prefix} ({self.plan}/{self.status})"

    # -------- Convenience helpers --------
    @property
    def is_active(self) -> bool:
        return self.status == "active" and self.revoked_at is None

    def is_trial(self) -> bool:
        return self.plan == "trial" and self.is_active

    def is_subscribed(self) -> bool:
        return self.plan != "trial" and self.is_active

<<<<<<< HEAD
    def revoke(self, when: timezone.datetime | None = None, save=True):
=======
    def revoke(self, when: timezone.datetime | None = None, save: bool = True):
>>>>>>> 610509e17015e87ecbab03f162f85fcbe64e03f2
        self.status = "revoked"
        self.revoked_at = when or timezone.now()
        if save:
            self.save(update_fields=["status", "revoked_at"])

<<<<<<< HEAD
    # Optional: safe DB-side increment (used if you don’t use Redis)
    def consume_one_trial_request(self) -> int:
        """
        Atomically increments used_requests in the DB and returns the new value.
        Use only for low/moderate traffic or as a fallback when cache is down.
=======
    def consume_one_trial_request(self) -> int:
        """
        Atomically increments used_requests in the DB and returns the new value.
        Use this only as a fallback when you don't use Redis/cache for counting.
>>>>>>> 610509e17015e87ecbab03f162f85fcbe64e03f2
        """
        if not self.is_trial():
            return self.used_requests
        type(self).objects.filter(pk=self.pk, status="active").update(
            used_requests=F("used_requests") + 1,
<<<<<<< HEAD
            last_used_at=timezone.now()
=======
            last_used_at=timezone.now(),
>>>>>>> 610509e17015e87ecbab03f162f85fcbe64e03f2
        )
        self.refresh_from_db(fields=["used_requests", "last_used_at"])
        return self.used_requests


class WebhookEvent(models.Model):
    """
    Optional: store processed webhook ids to ensure idempotency.
    """
    event_id = models.CharField(max_length=255, unique=True)
    kind = models.CharField(max_length=64)
    received_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.kind}:{self.event_id}"
