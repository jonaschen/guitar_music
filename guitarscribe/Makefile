.PHONY: build test analyze serve serve-frontend serve-stack clean lint shell

FILE ?= /app/fixtures/audio/test_progression.wav

build:
	docker compose build

test:
	docker compose run --rm backend pytest tests/ -v

analyze:
	@case "$(FILE)" in \
		/app/*) \
			docker compose run --rm backend python -m app.cli analyze "$(FILE)" --output /app/output/result.json ;; \
		*) \
			host_dir="$$(cd "$$(dirname "$(FILE)")" && pwd -P)"; \
			host_file="$$(basename "$(FILE)")"; \
			docker compose run --rm -v "$$host_dir:/input:ro" backend python -m app.cli analyze "/input/$$host_file" --output /app/output/result.json ;; \
	esac

serve:
	docker compose run --rm --service-ports backend python -m app.cli serve --host 0.0.0.0 --port 8000

serve-frontend:
	docker compose up frontend

serve-stack:
	docker compose up backend frontend

clean:
	rm -rf output/*
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name '*.pyc' -delete

lint:
	docker compose run --rm backend python -m ruff check app/ tests/ || true

shell:
	docker compose run --rm backend bash
