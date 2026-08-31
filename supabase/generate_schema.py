#!/usr/bin/env python3
"""Emits the Postgres schema from the SQLite one, so the two cannot drift.

The platform runs on SQLite locally - no install step, no service to start -
and on Supabase Postgres in production. Two hand-written schemas would
disagree within a month, and the disagreement would surface as a production-only
bug. So `musanga/db.py` stays the single source of truth and this script
translates it.

The translation is deliberately narrow. It does not try to modernise the
schema on the way through:

  * epoch seconds stay `bigint`, not `timestamptz`. Every timestamp in this
    codebase is an integer produced by `db.now()` and rendered by the browser,
    so converting at the database boundary would mean converting back in every
    handler.
  * flags stay `smallint` holding 0 or 1, because the queries compare them to
    1 and a boolean column would need every one of those rewritten.
  * money stays `bigint` ngwee, as it is everywhere else.

What it does add is what Postgres gives us and SQLite cannot: identity columns,
and row level security switched on with no policies at all - which denies the
anon and authenticated roles everything, while the service role the backend
uses bypasses RLS. A leaked anon key opens nothing.

Run: python3 supabase/generate_schema.py    (writes supabase/schema.sql)
"""

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from musanga import db  # noqa: E402

OUT = os.path.join(ROOT, "supabase", "schema.sql")

HEADER = """-- Musanga on Supabase Postgres.
--
-- GENERATED FILE - do not edit. Regenerate with:
--     python3 supabase/generate_schema.py
--
-- The source of truth is the SQLite schema in musanga/db.py. Everything here
-- is a mechanical translation of it, so the database the tests run against and
-- the database production runs on are the same shape.
--
-- Conventions carried over unchanged:
--   * money is integer ngwee (1 ZMW = 100 ngwee); only the view layer divides
--   * timestamps are epoch seconds as bigint, written by db.now()
--   * flags are smallint 0/1, because that is what the queries compare against
--   * references (MSG-xxxxxx, AGR-xxxxxx) are the human handle; ids are internal
--
-- Applying it is idempotent: every statement is IF NOT EXISTS or an
-- ADD COLUMN IF NOT EXISTS, so it doubles as the migration for a database that
-- already holds data.

"""

FOOTER = """
-- ---------------------------------------------------------------- security
--
-- Row level security on, with no policies defined. That is not an oversight:
-- the backend connects as the service role, which bypasses RLS entirely, and
-- every other role - including anon, the key that ships to browsers - is
-- denied every row. Authorisation lives in musanga/api.py, which is the only
-- thing that ever talks to this database.
--
-- If Supabase Auth is ever adopted for the browser to query directly, add
-- per-role policies here and nowhere else.
"""

TYPES = [
    (r"\bINTEGER PRIMARY KEY AUTOINCREMENT\b", "bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY"),
    (r"\bINTEGER\b", "bigint"),
    (r"\bREAL\b", "double precision"),
    (r"\bTEXT\b", "text"),
]

# Columns that hold 0 or 1. Kept numeric so `WHERE is_online = 1` still works,
# but narrowed to smallint so the intent is legible in the database too.
FLAG_COLUMNS = {
    "is_online", "is_export", "with_operator", "with_fuel", "with_waiver",
    "mandatory", "vat_registered", "cross_border", "is_control",
    "require_email", "allow_download", "link_disabled", "downloaded", "signed",
    "esign_consent", "authority_attested",
}


def split_statements(schema):
    """Statements, with SQL comments dropped - they carry across as prose in
    this file's own header, not as fragments of a CREATE TABLE.

    Comments come out *before* the split, not after. A comment is prose and
    prose contains semicolons; splitting first cuts such a comment in half and
    leaves the tail with no leading `--` to recognise it by, so it survives the
    strip and glues itself to the front of the next statement. That produced
    invalid SQL, and - because the CREATE TABLE was no longer the first thing
    in the statement - quietly dropped that table from the row level security
    list at the end of the file.
    """
    lines = [line for line in schema.splitlines() if not line.strip().startswith("--")]
    out = []
    for chunk in "\n".join(lines).split(";"):
        statement = chunk.strip()
        if statement:
            out.append(statement)
    return out


def translate_column(line):
    for pattern, replacement in TYPES:
        line = re.sub(pattern, replacement, line)
    name = line.strip().split(" ")[0]
    if name in FLAG_COLUMNS:
        line = line.replace("bigint", "smallint", 1)
    return line


def translate(statement):
    """One CREATE TABLE or CREATE INDEX, in Postgres."""
    if statement.upper().startswith("CREATE INDEX"):
        return statement + ";"

    head, body = statement.split("(", 1)
    body = body.rsplit(")", 1)[0]

    lines, depth, current = [], 0, ""
    for char in body:
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        if char == "," and depth == 0:
            lines.append(current)
            current = ""
            continue
        current += char
    lines.append(current)

    columns = [translate_column(line.strip()) for line in lines if line.strip()]
    return "%s(\n  %s\n);" % (head, ",\n  ".join(columns))


def added_columns():
    """The columns db.py adds by inspection on an existing SQLite database.
    Postgres has ADD COLUMN IF NOT EXISTS, so they are one statement each."""
    out = []
    for table, columns in (("orders", db.ORDER_COLUMNS), ("users", db.USER_COLUMNS),
                           ("agreements", db.AGREEMENT_COLUMNS),
                           ("quotes", db.QUOTE_COLUMNS),
                           ("rfp_bids", db.RFP_BID_COLUMNS),
                           ("rfps", db.RFP_COLUMNS)):
        for name, decl in columns:
            for pattern, replacement in TYPES:
                decl = re.sub(pattern, replacement, decl)
            if name in FLAG_COLUMNS:
                decl = decl.replace("bigint", "smallint", 1)
            out.append("alter table %s add column if not exists %s %s;" % (table, name, decl))
    return out


def table_names(statements):
    names = []
    for statement in statements:
        match = re.match(r"CREATE TABLE IF NOT EXISTS (\w+)", statement, re.I)
        if match:
            names.append(match.group(1))
    return names


def build():
    statements = split_statements(db.SCHEMA)
    parts = [HEADER]
    for statement in statements:
        parts.append(translate(statement))
        parts.append("")

    parts.append("-- ------------------------------------------------ later additions")
    parts.append("-- Columns that arrived after the first release. In SQLite these are")
    parts.append("-- applied by inspection; Postgres says it in one line.")
    parts += added_columns()
    parts.append("")

    parts.append(FOOTER)
    for name in table_names(statements):
        parts.append("alter table %s enable row level security;" % name)
    parts.append("")
    return "\n".join(parts)


def main():
    sql = build()
    with open(OUT, "w") as handle:
        handle.write(sql)
    print("  Wrote %s (%d statements, %.1f KB)"
          % (os.path.relpath(OUT, ROOT), sql.count(";"), len(sql) / 1024))


if __name__ == "__main__":
    main()
