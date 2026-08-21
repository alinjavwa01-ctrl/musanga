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

# Seed on first boot only, then serve. An existing database is left alone.
CMD ["sh", "-c", "python3 -c \"import os,sys; sys.path.insert(0,'.'); from musanga import db; sys.exit(0 if os.path.exists(db.DB_PATH) else 1)\" || python3 seed.py; exec python3 server.py"]
