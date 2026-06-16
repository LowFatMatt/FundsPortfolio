.PHONY: format lint test ci run docker-up docker-down

format:
	python -m ruff format .

lint:
	python -m ruff check .

test:
	python -m pytest tests/

ci: format lint test

run:
	PYTHONPATH=. python -m funds_portfolio.app

docker-up:
	docker compose up -d --build

docker-down:
	docker compose down
