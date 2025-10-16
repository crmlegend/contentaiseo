# billing/admin.py
from django.contrib import admin, messages
from django.utils import timezone
from .models import ApiKey

@admin.register(ApiKey)
class ApiKeyAdmin(admin.ModelAdmin):
    """
    Admin with everything you need for request-based trials:
    - See plan/status/quota/usage
    - Quick actions: set 10-try trial, flip to pro, revoke, reset usage
    """
    # TABLE LIST
    list_display = (
        "id",
        "user",
        "key_prefix",
        "plan",
        "status",
        "trial_quota",
        "used_requests",
        "last_used_at",
        "customer_id",
        "created_at",
        "revoked_at",
    )
    list_filter = ("plan", "status", "created_at")
    search_fields = ("user__username", "user__email", "key_prefix", "tenant_id", "customer_id", "key_hash")
    ordering = ("-created_at",)

    # FORM LAYOUT
    readonly_fields = ("created_at", "revoked_at", "last_used_at", "used_requests", "key_hash", "key_prefix", "plain_suffix")
    fieldsets = (
        ("Key & Ownership", {
            "fields": ("user", "tenant_id", "key_prefix", "key_hash", "plain_suffix"),
        }),
        ("Plan & Lifecycle", {
            "fields": ("plan", "status", "created_at", "revoked_at", "customer_id"),
        }),
        ("Trial (Request-based)", {
            "fields": ("trial_quota", "used_requests", "last_used_at"),
            "description": "For trial keys, set trial_quota (e.g., 10). used_requests increments as the API is called.",
        }),
    )

    # BULK ACTIONS
    actions = ["set_trial_10", "flip_to_pro", "revoke_keys", "reset_trial_usage"]

    @admin.action(description="Set selected keys to TRIAL (10 requests) and activate")
    def set_trial_10(self, request, queryset):
        updated = queryset.update(
            plan="trial",
            status="active",
            revoked_at=None,
            trial_quota=10,
        )
        messages.success(request, f"{updated} key(s) set to TRIAL (10).")

    @admin.action(description="Flip selected keys to PRO (paid) and activate")
    def flip_to_pro(self, request, queryset):
        updated = queryset.update(
            plan="pro",
            status="active",
            revoked_at=None,
            trial_quota=None,  # paid keys don't use request quota
        )
        messages.success(request, f"{updated} key(s) flipped to PRO.")

    @admin.action(description="Revoke selected keys")
    def revoke_keys(self, request, queryset):
        now = timezone.now()
        updated = queryset.exclude(status="revoked").update(status="revoked", revoked_at=now)
        messages.warning(request, f"{updated} key(s) revoked.")

    @admin.action(description="Reset trial usage (used_requests=0) for selected keys")
    def reset_trial_usage(self, request, queryset):
        qs = queryset.filter(plan="trial")
        updated = qs.update(used_requests=0, last_used_at=None)
        messages.success(request, f"Reset usage for {updated} trial key(s).")
