# Flash — raccourcis de développement (INFRA-004).
# `make` sans argument affiche l'aide.

COMPOSE ?= docker compose -f infra/docker-compose.yml
BACKEND ?= backend
WEB     ?= web

.DEFAULT_GOAL := help
.PHONY: help up up-web down down-v logs ps migrate makemigration seed reference \
        openapi shell dbshell test test-backend test-web lint fmt build clean

help: ## Affiche cette aide
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

## ─────────────────────────────────────────────────────── pile locale (Docker)
up: ## Démarre db + redis + mailhog + api
	$(COMPOSE) up --build

up-web: ## Idem + le SPA (profil web)
	$(COMPOSE) --profile web up --build

down: ## Arrête la pile (garde les volumes)
	$(COMPOSE) down

down-v: ## Arrête la pile ET supprime les volumes (base remise à zéro)
	$(COMPOSE) down -v

logs: ## Suit les logs de l'API (make logs SVC=web pour un autre service)
	$(COMPOSE) logs -f $(or $(SVC),api)

ps: ## État des services
	$(COMPOSE) ps

## ─────────────────────────────────────────────────────── base de données
migrate: ## Applique les migrations Alembic dans le conteneur api
	$(COMPOSE) exec api flash db upgrade

makemigration: ## Génère une révision Alembic (make makemigration M="message")
	$(COMPOSE) exec api flash db revision -m "$(M)"

seed: ## Jeu de démo (agent + marchand + 2 utilisateurs approvisionnés)
	$(COMPOSE) exec api flash seed

reference: ## (Re)charge le référentiel pays / opérateurs
	$(COMPOSE) exec api flash reference seed

dbshell: ## Ouvre psql sur la base de dev
	$(COMPOSE) exec db psql -U flash -d flash

shell: ## Shell dans le conteneur api
	$(COMPOSE) exec api sh

## ─────────────────────────────────────────────────────── qualité
openapi: ## Régénère docs/api/openapi.json + le client TS du web
	cd $(BACKEND) && flash openapi dump -o ../docs/api/openapi.json
	cd $(WEB) && npm run gen:api

lint: ## Lint backend (ruff + mypy) et web (eslint + prettier)
	cd $(BACKEND) && ruff check src tests && mypy src
	cd $(WEB) && npm run lint

fmt: ## Formate backend (ruff format) et web (prettier)
	cd $(BACKEND) && ruff format src tests && ruff check --fix src tests
	cd $(WEB) && npm run format

test: test-backend test-web ## Lance toute la suite de tests

test-backend: ## Tests backend (hors contrat schemathesis)
	cd $(BACKEND) && pytest -m "not contract"

test-web: ## Tests web (Vitest + couverture features/)
	cd $(WEB) && npm run test:cov

build: ## Build de production des deux images
	docker build -f $(BACKEND)/Dockerfile --target prod -t flash-api:local .
	docker build -f $(WEB)/Dockerfile --target runtime -t flash-web:local $(WEB)

clean: ## Nettoie les artefacts de build locaux
	rm -rf $(WEB)/dist $(WEB)/coverage $(WEB)/.lighthouseci $(BACKEND)/.coverage $(BACKEND)/coverage.xml
