FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Production runs PostgreSQL 18. Keep pg_dump on the same major so portable
# custom-format backups remain compatible with the live database.
RUN apt-get update && \
    apt-get install -y --no-install-recommends ca-certificates curl && \
    install -d /usr/share/postgresql-common/pgdg && \
    curl -fsSLo /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc \
      https://www.postgresql.org/media/keys/ACCC4CF8.asc && \
    echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt bookworm-pgdg main" \
      > /etc/apt/sources.list.d/pgdg.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends postgresql-client-18 && \
    apt-get purge -y --auto-remove curl && \
    rm -rf /var/lib/apt/lists/*

RUN groupadd --system app && \
    useradd --system --gid app --create-home app && \
    mkdir -p /home/app/.cache && \
    chown -R app:app /home/app/.cache

COPY pyproject.toml README.md alembic.ini ./
COPY app ./app
COPY config ./config
COPY migrations ./migrations
RUN python -m pip install --upgrade pip "setuptools>=78.1.1" && \
    python -m pip install . && \
    python -m pip check

USER app
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
