# Musanga runs on the Python standard library alone, so the image is just
# Python plus the source. No package manager, no build step, no lockfile.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    MUSANGA_ENV=production \
    MUSANGA_DB=/data/musanga.db \
    HOST=0.0.0.0 \
    PORT=8080

WORKDIR /app
COPY . .

# Version the asset URLs at build time so the deployed HTML points at the
# files it actually shipped with.
RUN python3 stamp.py

# SQLite needs somewhere durable; mount a volume here.
VOLUME ["/data"]
EXPOSE 8080

# The demo accounts share one password that is published in the README, so a
# public deployment starts with an empty database. Set MUSANGA_SEED=demo to
# load the demo loads, hires and accounts instead - only for a showcase you are
# happy for anyone to sign into. Either way an existing database is untouched.
CMD ["sh", "-c", "python3 boot.py && exec python3 server.py"]
