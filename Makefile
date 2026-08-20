.PHONY: install dev test lint up down logs

install:
	python -m pip install -e ".[dev]"

dev:
	uvicorn app.main:app --reload

test:
	pytest -q

lint:
	ruff check .

up:
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f
