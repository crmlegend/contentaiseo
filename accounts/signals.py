# accounts/signals.py
import logging
from django.conf import settings
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model

from billing.models import ApiKey
from billing.utils import issue_trial_key_for_user

logger = logging.getLogger(__name__)
User = get_user_model()

# You can override this in settings.py (e.g., FREE_TRIAL_QUOTA = 10)
DEFAULT_TRIAL_QUOTA = getattr(settings, "FREE_TRIAL_QUOTA", 5)

@receiver(post_save, sender=User)
def create_trial_key(sender, instance: User, created: bool, **kwargs):
    """
    When a brand-new user is created, issue a trial API key with N free requests.
    - Skips if a key already exists (safety/idempotency).
    - Uses on_commit so it only runs after the user row is committed.
    """
    if not created:
        return

    # Optional: skip staff/superusers (uncomment if you don't want to give them trials)
    # if instance.is_staff or instance.is_superuser:
    #     return

    def _issue():
        try:
            # Safety: if something else already created a key, do nothing.
            exists = ApiKey.objects.filter(user=instance, status="active").exists()
            if exists:
                logger.info("Trial key not issued; active key already exists for user %s", instance.id)
                return

            raw = issue_trial_key_for_user(user=instance, quota=int(DEFAULT_TRIAL_QUOTA))
            logger.info("Issued trial key for user %s (quota=%s)", instance.id, DEFAULT_TRIAL_QUOTA)
            # NOTE: 'raw' is the full key; do not log/return it in production.
        except Exception as e:
            logger.exception("Failed to issue trial key for user %s: %s", instance.id, e)

    # Ensure we run only after the user insert is committed
    transaction.on_commit(_issue)
