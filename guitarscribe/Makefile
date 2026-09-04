.PHONY: build test analyze clean lint shell

FILE ?= /app/fixtures/audio/test_progression.wav

build:
	docker compose build

test:
	docker compose run --rm backend pytest tests/ -v

analyze:
	docker compose run --rm backend python -m app.cli analyze $(FILE) --output /app/output/result.json

clean:
	rm -rf output/*
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name '*.pyc' -delete

lint:
	docker compose run --rm backend python -m ruff check app/ tests/ || true

shell:
	docker compose run --rm backend bash
