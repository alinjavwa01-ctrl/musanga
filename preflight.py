#!/usr/bin/env python3
"""Is this deployment actually ready? Run it before pointing a domain at one.

    python3 preflight.py

Every check is one thing that has bitten a real deployment: a database nobody
can reach, a schema a release older than the code, demo accounts live on a
public URL with a password printed in a README, sessions that never expire, a
server still handing tracebacks to strangers.

Exit status is 0 when everything that must pass, passes. Warnings do not fail
the run - they are the things a staging deployment may legitimately have and a
production one should not.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from musanga import config, db  # noqa: E402

config.load_env()

FAILURES = []
WARNINGS = []


def ok(message):
    print("  ok    %s" % message)


def fail(message, fix=""):
    FAILURES.append((message, fix))
    print("  FAIL  %s" % message)
    if fix:
        print("        %s" % fix)


def warn(message, fix=""):
    WARNINGS.append((message, fix))
    print("  warn  %s" % message)
    if fix:
        print("        %s" % fix)


def check_environment():
    print("\n  Environment")
    for key, value in sorted(config.describe().items()):
        print("    %-13s %s" % (key, value))

    if not config.production():
        warn("MUSANGA_ENV is not 'production'",
             "Assets will not be cached, HSTS is off, and errors are verbose.")
    else:
        ok("running in production mode")


def check_database():
    print("\n  Database")
    if not db.postgres():
        warn("running on SQLite, not Postgres",
             "Fine for one machine with a volume. Set DATABASE_URL for Supabase.")
    try:
        conn = db.connect()
    except Exception as e:  # noqa: BLE001 - the point of the check
        return fail("cannot connect: %s" % e,
                    "Check DATABASE_URL, the password, and that the host allows this address.")
    try:
        conn.execute("SELECT 1").fetchone()
        ok("connected")
        check_schema(conn)
        check_data(conn)
    finally:
        conn.close()


def check_schema(conn):
    """Every table the code expects, present in the database it is pointed at."""
    expected = set()
    for statement in db.SCHEMA.split(";"):
        line = statement.strip()
        if line.upper().startswith("CREATE TABLE IF NOT EXISTS"):
            expected.add(line.split()[5].lower())

    if db.postgres():
        rows = conn.execute("SELECT tablename AS name FROM pg_tables WHERE schemaname = 'public'")
    else:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    present = {r["name"].lower() for r in rows.fetchall()}

    missing = sorted(expected - present)
    if missing:
        fail("schema is behind the code: %s" % ", ".join(missing),
             "Run: python3 boot.py")
    else:
        ok("schema has all %d tables" % len(expected))

    # The generated Postgres schema must match the SQLite one it came from.
    generated = os.path.join(os.path.dirname(os.path.abspath(__file__)), "supabase", "schema.sql")
    if os.path.isfile(generated):
        sys.path.insert(0, os.path.dirname(generated))
        from supabase.generate_schema import build  # noqa: E402
        with open(generated) as handle:
            if handle.read() != build():
                fail("supabase/schema.sql is stale",
                     "Run: python3 supabase/generate_schema.py")
            else:
                ok("supabase/schema.sql matches musanga/db.py")


def check_data(conn):
    demo = conn.execute(
        "SELECT COUNT(*) AS n FROM users WHERE phone IN ('+260970000001','+260971000001')"
    ).fetchone()["n"]
    if demo and config.production():
        fail("demo accounts exist on a production deployment",
             "Every demo account shares one password printed in the README. "
             "Drop them, or seed nothing and register the first account through sign-up.")
    elif demo:
        warn("demo accounts are present (%d)" % demo, "Expected on a showcase, not in production.")
    else:
        ok("no demo accounts")

    if os.environ.get("MUSANGA_SEED") == "demo" and config.production():
        fail("MUSANGA_SEED=demo is set in production",
             "Unset it. It only fires on an empty database, but it should not be armed.")

    ops = conn.execute("SELECT COUNT(*) AS n FROM users WHERE role = 'ops'").fetchone()["n"]
    if not ops:
        warn("no control account exists",
             "Nobody can review a KYC file or send a contract until one does.")
    else:
        ok("%d control account(s)" % ops)


def check_security():
    print("\n  Security")
    from musanga import api

    if api.SESSION_DAYS > 30:
        warn("sessions last %d days" % api.SESSION_DAYS, "Set MUSANGA_SESSION_DAYS lower.")
    else:
        ok("sessions expire after %d days" % api.SESSION_DAYS)

    if db.postgres() and (os.environ.get("MUSANGA_DB_SSL") or "verify") != "verify":
        warn("database TLS certificate verification is off",
             "MUSANGA_DB_SSL=verify unless the host's certificate is genuinely private.")
    elif db.postgres():
        ok("database TLS is verified")

    if os.environ.get("SUPABASE_SERVICE_KEY") and not config.production():
        warn("a service-role key is set outside production",
             "That key bypasses row level security. Keep it off developer machines.")

    env_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.isfile(env_file):
        import subprocess
        tracked = subprocess.run(["git", "check-ignore", "-q", ".env"],
                                 cwd=os.path.dirname(env_file)).returncode == 0
        if tracked:
            ok(".env exists and is gitignored")
        else:
            fail(".env is not gitignored", "Add '.env' to .gitignore before committing anything.")


def check_assets():
    print("\n  Build")
    import stamp
    changed = []
    web = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
    for name in sorted(os.listdir(web)):
        if not name.endswith(".html"):
            continue
        path = os.path.join(web, name)
        with open(path) as handle:
            before = handle.read()
        after = stamp.PATTERN.sub(stamp.stamp, before)
        if before != after:
            changed.append(name)
    if changed:
        fail("asset URLs are stale in %s" % ", ".join(changed), "Run: python3 stamp.py")
    else:
        ok("asset URLs match the files on disk")


def main():
    print("\n  Musanga pre-flight")
    check_environment()
    check_database()
    check_security()
    check_assets()

    print("")
    if FAILURES:
        print("  %d blocking, %d warning(s). Not ready." % (len(FAILURES), len(WARNINGS)))
        return 1
    print("  Ready. %d warning(s)." % len(WARNINGS))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
