"""Configuration, read once from the environment.

Two things live here. The first is a .env reader: a deployment sets real
environment variables, but a developer pointing a local run at a staging
database should not have to export five things by hand every session, and a
secret in a gitignored file beats a secret in shell history.

The second is `describe()`, which is what the pre-flight check and the boot
log print. It never returns a secret - only whether one is set, and the host it
points at - because those lines end up in logs.
"""

import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_FILE = os.path.join(ROOT, ".env")

SECRET_KEYS = ("DATABASE_URL", "SUPABASE_DB_URL", "SUPABASE_SERVICE_KEY", "PASSWORD")


def load_env(path=ENV_FILE):
    """Fill in anything the environment does not already define.

    A real environment variable always wins, so a deployment cannot be
    surprised by a stray file left in the image.
    """
    if not os.path.isfile(path):
        return []
    loaded = []
    with open(path) as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key, value = key.strip(), value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
                loaded.append(key)
    return loaded


def production():
    return os.environ.get("MUSANGA_ENV") == "production"


def redact(key, value):
    if not value:
        return "unset"
    if any(secret in key.upper() for secret in SECRET_KEYS):
        # Enough to tell two databases apart in a log, not enough to use.
        if "@" in value:
            return "…@" + value.split("@", 1)[1]
        return "set (%d chars)" % len(value)
    return value


def describe():
    """What this process is configured to do, safe to print."""
    from . import db
    return {
        "environment": os.environ.get("MUSANGA_ENV") or "development",
        "database": "postgres" if db.postgres() else "sqlite (%s)" % db.DB_PATH,
        "database_url": redact("DATABASE_URL", os.environ.get("DATABASE_URL")
                               or os.environ.get("SUPABASE_DB_URL")),
        "ssl": os.environ.get("MUSANGA_DB_SSL") or "verify",
        "session_days": os.environ.get("MUSANGA_SESSION_DAYS") or "14",
        "seed": os.environ.get("MUSANGA_SEED") or "unset",
    }
