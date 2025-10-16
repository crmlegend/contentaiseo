# accounts/apps.py
from django.apps import AppConfig
import logging

logger = logging.getLogger(__name__)

class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "accounts"
    verbose_name = "Accounts"

    def ready(self):
        # Import signal receivers so Django registers them when the app loads
        try:
            from . import signals  # noqa: F401
        except Exception as exc:
            # Don't crash the app if something goes wrong; log for debugging
            logger.exception("Failed to load accounts.signals: %s", exc)



