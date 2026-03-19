.PHONY: format lint test ci run docker-up docker-down

format:
	python -m ruff format .

lint:
	python -m ruff check .

test:
	python -m pytest

ci: format lint test

run:
	PYTHONPATH=. python -m funds_portfolio.app

docker-up:
	docker compose up --build

docker-down:
	docker compose down
