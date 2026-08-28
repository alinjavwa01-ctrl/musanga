#!/usr/bin/env python3
"""The Postgres compatibility layer, without a Postgres.

The translation from SQLite's dialect to Postgres' is small and mechanical,
which is exactly the kind of code that breaks quietly. These run anywhere, with
no database and no driver installed, so a broken translation fails in CI rather
than in production.

Usage: python3 tests_pg.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from musanga import db, pgdb  # noqa: E402

PASS = FAIL = 0


def check(name, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ok    %s" % name)
    else:
        FAIL += 1
        print("  FAIL  %s  %s" % (name, extra))


# --- statement translation -------------------------------------------------
t = pgdb.translate

sql = t("INSERT INTO users (role, name) VALUES (?,?)")
check("an insert into a table with an id returns it", sql.endswith("RETURNING id"), sql)

sql = t("INSERT INTO sessions (token, user_id, created_at) VALUES (?,?,?)")
check("a table without an id column does not", "RETURNING" not in sql, sql)

sql = t("INSERT OR IGNORE INTO order_documents (order_id, doc_key) VALUES (?,?)")
check("INSERT OR IGNORE becomes ON CONFLICT DO NOTHING", "ON CONFLICT DO NOTHING" in sql, sql)
check("and still returns the id", sql.strip().endswith("RETURNING id"), sql)

sql = t("INSERT INTO kyc_documents (user_id, doc_key) VALUES (?,?) "
        "ON CONFLICT (user_id, doc_key) DO UPDATE SET doc_key = excluded.doc_key")
check("an explicit upsert is left alone", sql.count("ON CONFLICT") == 1, sql)

check("PRAGMA is skipped entirely", t("PRAGMA table_info(orders)") is None)
check("a select is untouched", t("SELECT * FROM users WHERE id = ?") == "SELECT * FROM users WHERE id = ?")
check("placeholders are not rewritten", "?" in t("UPDATE users SET name = ? WHERE id = ?"))
check("translation is cached", t("SELECT 1") is t("SELECT 1"))

# Every table the app inserts into with lastrowid must be known to the layer.
check("id tables come from the schema, not a hand list",
      {"users", "orders", "agreements", "kyc_people"} <= pgdb._id_tables(),
      sorted(pgdb._id_tables())[:5])
check("keyed tables are excluded",
      not ({"sessions", "kyc_profiles"} & pgdb._id_tables()),
      sorted(pgdb._id_tables()))

# --- rows behave like sqlite3.Row -----------------------------------------
row = pgdb.Row(["id", "name", "company"], [7, "Ann", None])
check("a row reads by name", row["name"] == "Ann")
check("a row reads by index", row[0] == 7)
check("a row converts to a dict", dict(row) == {"id": 7, "name": "Ann", "company": None})
try:
    row["nope"]
    check("a missing column raises KeyError", False)
except KeyError:
    check("a missing column raises KeyError", True)
check("get() has a default", row.get("nope", "fallback") == "fallback")
check("membership works", "company" in row and "nope" not in row)

# --- the script splitter --------------------------------------------------
script = """
-- a comment with a ; semicolon in it
create table a (id bigint);
create table b (name text default 'x;y');
"""
statements = pgdb._split_script(script)
check("the splitter ignores semicolons in comments and strings",
      len(statements) == 2 and statements[1].endswith("'x;y')"), statements)

# --- the generated schema covers the code ---------------------------------
schema_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "supabase", "schema.sql")
with open(schema_path) as handle:
    schema = handle.read().lower()

expected = [line.strip().split()[5].lower()
            for line in db.SCHEMA.split(";")
            if line.strip().upper().startswith("CREATE TABLE IF NOT EXISTS")]
missing = [name for name in expected if "create table if not exists %s" % name not in schema]
check("every SQLite table is in the Postgres schema", not missing, missing)

added = [name for name, _ in db.ORDER_COLUMNS] + [name for name, _ in db.USER_COLUMNS]
missing = [name for name in added if "add column if not exists %s " % name not in schema]
check("every later column is in the Postgres schema", not missing, missing)

check("epoch timestamps stay integers", "created_at bigint" in schema, "")
check("flags are narrowed to smallint", "is_online   smallint" in schema, "")
check("row level security is switched on everywhere",
      schema.count("enable row level security") == len(expected), schema.count("enable row level security"))
check("no policy grants anything by default", "create policy" not in schema)

print("\n  %d passed, %d failed" % (PASS, FAIL))
raise SystemExit(1 if FAIL else 0)
