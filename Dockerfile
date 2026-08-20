FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN groupadd --system app && \
    useradd --system --gid app --create-home app && \
    mkdir -p /home/app/.cache && \
    chown -R app:app /home/app/.cache

COPY pyproject.toml README.md alembic.ini ./
COPY app ./app
COPY config ./config
COPY migrations ./migrations
RUN pip install --upgrade pip && pip install .

USER app
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
