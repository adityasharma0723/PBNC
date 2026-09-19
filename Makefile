.PHONY: up down build test migrate lint demo clean

up:
	docker compose up --build -d

down:
	docker compose down

build:
	docker compose build

test:
	docker compose run --rm -e EXTRACTOR=fake -e DATABASE_URL=sqlite+aiosqlite:///test.db api \
		python -m pytest tests/ -v --tb=short

migrate:
	docker compose exec api alembic upgrade head

lint:
	docker compose exec api python -m py_compile app/main.py

demo:
	docker compose exec api python scripts/run_demo.py

clean:
	docker compose down -v --remove-orphans
