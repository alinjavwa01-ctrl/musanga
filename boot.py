#!/usr/bin/env python3
"""First-boot database setup, and the migration on every boot after that.

`db.init()` is idempotent - it creates any missing table and adds any missing
column - so it runs on every boot, not only the first. That is what carries a
deployed database across a release that adds tables: without it, a volume that
already holds a database would keep the schema it was created with and the new
code would fail against it.

Demo data is loaded only when there was no database at all and MUSANGA_SEED=demo
is set, because the demo accounts share one password that is published in the
README - fine for a showcase, not for anything real. Existing data is never
touched, and seeding never runs against a database that already exists.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from musanga import db  # noqa: E402


def main():
    existed = os.path.exists(db.DB_PATH)

    parent = os.path.dirname(db.DB_PATH)
    if parent and not os.path.isdir(parent):
        os.makedirs(parent, exist_ok=True)

    if existed:
        # Bring the schema up to what this release expects, and leave every
        # row where it is.
        before = _schema_shape()
        db.init().close()
        after = _schema_shape()
        added_tables = sorted(after["tables"] - before["tables"])
        added_columns = sorted(after["columns"] - before["columns"])
        if added_tables or added_columns:
            print("  Migrated %s:" % db.DB_PATH)
            for name in added_tables:
                print("    + table  %s" % name)
            for name in added_columns:
                print("    + column orders.%s" % name)
        else:
            print("  Database at %s is already up to date." % db.DB_PATH)
        return

    if os.environ.get("MUSANGA_SEED") == "demo":
        from seed import seed
        seed()
        print("  WARNING: demo accounts are live and share a published password.")
    else:
        db.init().close()
        print("  Empty database created at %s." % db.DB_PATH)
        print("  Register the first account through the sign-up form.")


def _schema_shape():
    """What the database holds right now, so a migration can report itself."""
    conn = db.connect()
    try:
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'")}
        columns = set()
        if "orders" in tables:
            columns = {r["name"] for r in conn.execute("PRAGMA table_info(orders)")}
        return {"tables": tables, "columns": columns}
    finally:
        conn.close()


if __name__ == "__main__":
    main()
