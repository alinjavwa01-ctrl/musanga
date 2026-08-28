# Musanga runs on the standard library plus one pure-Python Postgres driver,
# so the image is Python, pip install of a single wheel, and the source.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    MUSANGA_ENV=production \
    MUSANGA_DB=/data/musanga.db \
    HOST=0.0.0.0 \
    PORT=8080

# Set DATABASE_URL to a Supabase Postgres URL and the volume below is unused:
# boot.py applies the schema there instead and nothing is written to disk.

WORKDIR /app

# Dependencies first, so a source edit does not reinstall them.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Version the asset URLs at build time so the deployed HTML points at the
# files it actually shipped with.
RUN python3 stamp.py

# SQLite needs somewhere durable; mount a volume here. Not needed when
# DATABASE_URL points at Postgres.
VOLUME ["/data"]
EXPOSE 8080

# The demo accounts share one password that is published in the README, so a
# public deployment starts with an empty database. Set MUSANGA_SEED=demo to
# load the demo loads, hires and accounts instead - only for a showcase you are
# happy for anyone to sign into. Either way an existing database is untouched.
CMD ["sh", "-c", "python3 boot.py && exec python3 server.py"]
