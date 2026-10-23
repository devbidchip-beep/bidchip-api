"""
Development settings — local developer machines only.
Never deploy these settings to production.
"""

from decouple import config

from .base import *  # noqa: F401, F403

# ---------------------------------------------------------------------------
# Debug
# ---------------------------------------------------------------------------
DEBUG = True

ALLOWED_HOSTS = ["*"]

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
# Prefer DATABASE_URL from .env; fall back to local postgres, then SQLite.
_database_url = config("DATABASE_URL", default="")

if _database_url:
    import dj_database_url

    DATABASES = {
        "default": dj_database_url.parse(_database_url, conn_max_age=600),
    }
else:
    # SQLite fallback for quick local setup without PostgreSQL
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",  # noqa: F405
        }
    }

# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
CORS_ALLOW_ALL_ORIGINS = True

# ---------------------------------------------------------------------------
# Django debug toolbar (optional — install separately if needed)
# ---------------------------------------------------------------------------
# INSTALLED_APPS += ["debug_toolbar"]
# MIDDLEWARE = ["debug_toolbar.middleware.DebugToolbarMiddleware"] + MIDDLEWARE

# ---------------------------------------------------------------------------
# django-allauth (relax email verification in dev)
# ---------------------------------------------------------------------------
ACCOUNT_EMAIL_VERIFICATION = "optional"

# ---------------------------------------------------------------------------
# Django Extensions / shell_plus (optional)
# ---------------------------------------------------------------------------
# INSTALLED_APPS += ["django_extensions"]
