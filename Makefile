.PHONY: test lint typecheck up seed
up:
	docker compose up --build -d
seed:
	docker compose exec api python -m packages.common.cli seed
test:
	python -m pytest -q
lint:
	python -m ruff check .
typecheck:
	python -m mypy apps packages
