.PHONY: demo up down migrate seed api install

# Roda AGORA, sem banco: prova o motor de calendário duplo.
demo:
	python3 scripts/demo_local.py

install:
	python3 -m pip install -r requirements.txt

up:
	docker compose up -d

down:
	docker compose down

migrate:
	python3 scripts/migrate.py

seed:
	python3 scripts/seed.py

api:
	uvicorn api.main:app --reload
