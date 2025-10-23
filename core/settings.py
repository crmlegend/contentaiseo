from pathlib import Path
import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# ---------------- Security / Env ----------------
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "devsecret")  # local fallback only
DEBUG = os.getenv("DEBUG", "0") == "1"

# Your public hostnames (no schemes, no slashes)
ALLOWED_HOSTS = [
    "contentaiseo.com",
    "www.contentaiseo.com",
    "contentseoai-c2ahaybrcha9hkcw.canadacentral-01.azurewebsites.net",
]

ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")
TEST_KEY = os.getenv("TEST_KEY", "")
JWT_ISS = os.getenv("JWT_ISS", "")

# Stripe
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY", "")
STRIPE_PRICE_ID = os.getenv("STRIPE_PRICE_ID", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")

# API keys
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# Detect Azure App Service
IS_AZURE = bool(os.environ.get("WEBSITE_SITE_NAME"))

def _safe_mkdir(path: str) -> None:
    try:
        os.makedirs(path, exist_ok=True)
    except PermissionError:
        pass

# ---------------- Installed apps ----------------
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # 3rd party
    "rest_framework",
    "corsheaders",
    # local
    "accounts.apps.AccountsConfig",
    "billing",
    "content",
]

# ---------------- Security / cookies / proxy ----------------
# Azure runs behind a reverse proxy and terminates TLS there.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True

# Use secure cookies in prod
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SECURE = True

# Keep cookies same-site to avoid accidental cross-site sends
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SAMESITE = "Lax"

# Allow cookies to be valid on both root and www subdomains
CSRF_COOKIE_DOMAIN = ".contentaiseo.com"
SESSION_COOKIE_DOMAIN = ".contentaiseo.com"

# ---------------- CORS / CSRF ----------------
# Goal: eliminate CSRF problems for APIs by not using cookies across origins.
# Allow any origin for API *without* credentials. Forms on your own site still use CSRF.
CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOW_CREDENTIALS = False  # critical to avoid cross-site cookies/CSRF

# If you ever *must* send credentials from a specific frontend origin,
# switch to:
# CORS_ALLOW_ALL_ORIGINS = False
# CORS_ALLOWED_ORIGINS = ["https://contentaiseo.com", "https://www.contentaiseo.com"]
# CORS_ALLOW_CREDENTIALS = True
# ...and ensure your JS includes credentials + X-CSRFToken.

# Origins that are allowed to set the CSRF cookie and submit POST forms
CSRF_TRUSTED_ORIGINS = [
    "https://contentaiseo.com",
    "https://www.contentaiseo.com",
    "https://contentseoai-c2ahaybrcha9hkcw.canadacentral-01.azurewebsites.net",
]

# ---------------- Middleware ----------------
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",  # keep: protects your Django forms
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]

# ---------------- Templates ----------------
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

ROOT_URLCONF = "core.urls"
WSGI_APPLICATION = "core.wsgi.application"

# ---------------- Database (SQLite with Azure-safe path) ----------------
SQLITE_PATH = os.getenv(
    "SQLITE_PATH",
    "/home/data/app.db" if IS_AZURE else str(BASE_DIR / "db.sqlite3"),
)
_sqlite_dir = os.path.dirname(SQLITE_PATH)
if SQLITE_PATH.startswith("/home/") or SQLITE_PATH.startswith(str(BASE_DIR)):
    _safe_mkdir(_sqlite_dir)

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": SQLITE_PATH,
        "OPTIONS": {"timeout": 20},
    }
}

# ---------------- Auth ----------------
AUTH_USER_MODEL = "accounts.User"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------------- I18N ----------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# ---------------- Static (WhiteNoise) ----------------
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    }
}

# ---------------- Media ----------------
MEDIA_URL = "/media/"
MEDIA_ROOT = os.getenv("MEDIA_ROOT", "/home/data/media" if IS_AZURE else str(BASE_DIR / "media"))
if MEDIA_ROOT.startswith("/home/") or MEDIA_ROOT.startswith(str(BASE_DIR)):
    _safe_mkdir(MEDIA_ROOT)

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------- DRF ----------------
# IMPORTANT: No SessionAuthentication => no CSRF required for API views.
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "billing.auth.ApiKeyAuthentication",
    ],
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.UserRateThrottle",
        "rest_framework.throttling.AnonRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {"user": "60/min", "anon": "10/min"},
}

# ---------------- Celery (note: needs a worker/Redis to actually run) ----------------
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")

LOGIN_REDIRECT_URL = "/dashboard/"
LOGIN_URL = "login"
LOGOUT_REDIRECT_URL = "/accounts/login/"

# ---------------- Logging ----------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": os.getenv("DJANGO_LOG_LEVEL", "INFO")},
    "loggers": {
        "django": {"handlers": ["console"], "level": "INFO", "propagate": True},
        "django.request": {"handlers": ["console"], "level": "ERROR", "propagate": False},
    },
}
