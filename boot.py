#!/usr/bin/env python3
"""First-boot database setup.

Creates the schema if there is no database yet. Demo data is loaded only when
MUSANGA_SEED=demo is set, because the demo accounts all share one password that
is published in the README - fine for a showcase, not for anything real.

An existing database is never touched.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from musanga import db  # noqa: E402


def main():
    if os.path.exists(db.DB_PATH):
        print("  Database already present at %s, leaving it alone." % db.DB_PATH)
        return

    parent = os.path.dirname(db.DB_PATH)
    if parent and not os.path.isdir(parent):
        os.makedirs(parent, exist_ok=True)

    if os.environ.get("MUSANGA_SEED") == "demo":
        from seed import seed
        seed()
        print("  WARNING: demo accounts are live and share a published password.")
    else:
        db.init().close()
        print("  Empty database created at %s." % db.DB_PATH)
        print("  Register the first account through the sign-up form.")


if __name__ == "__main__":
    main()
