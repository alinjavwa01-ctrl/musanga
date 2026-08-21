#!/usr/bin/env bash
# Start Musanga. No install step - Python 3's standard library is the whole
# dependency list.
set -euo pipefail
cd "$(dirname "$0")"

PORT="${PORT:-8000}"

# Version the asset URLs so an edit can never be shadowed by a cached copy.
python3 stamp.py

if [ ! -f musanga.db ]; then
  echo "  No database found, seeding demo data…"
  python3 seed.py
fi

exec python3 server.py --port "$PORT" "$@"
