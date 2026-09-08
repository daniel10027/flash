# Flash — Backend

API et cœur métier. Architecture hexagonale (voir `../docs/architecture.md` et
`../docs/decisions/`).

```
src/flash/
├── domain/          # entités, VO, agrégats, invariants, ports — AUCUN import externe
│   ├── shared/      # Money/Currency, identifiants, erreurs, événements, ports transverses
│   ├── identity/    # User + PhoneNumber (1 à 5)
│   ├── wallet/      # Wallet (disponible / réservé)
│   ├── ledger/      # partie double : LedgerAccount, Posting, LedgerTransaction
│   ├── pricing/     # PricingService (frais 0,8 %)
│   └── limits/      # LimitPolicy, KycPolicy
├── application/     # cas d'usage, Unit of Work, idempotence, publication d'événements
├── infrastructure/  # adapters : SQLAlchemy, Redis, FCM, SMTP, passerelles sandbox
└── interface/       # Flask (API), CLI, jobs, génération OpenAPI
```

## Développement

```bash
python3.12 -m venv .venv
.venv/bin/pip install -e ".[dev]"

.venv/bin/pytest                 # tests + couverture (seuil 90 % sur domain/ + application/)
.venv/bin/ruff check src tests   # lint
.venv/bin/ruff format src tests  # formatage
.venv/bin/mypy src/flash tests   # typage strict
```

En local via Docker (à partir de la tâche `INFRA-001`) : `docker compose -f
../infra/docker-compose.yml up`.

## Règles

- `domain/` n'importe ni Flask, ni SQLAlchemy, ni Redis, ni `requests`, ni `pydantic`.
  Vérifié par `tests/architecture/` (tâche `BE-023`) et par `ruff` (imports bannis).
- Tout montant est un `Money` (entier d'unités mineures + devise), jamais un `float`.
- Toute opération monétaire passe par une `LedgerTransaction` équilibrée et accepte une
  clé d'idempotence.
- Une tâche du backlog (`../docs/tasks/backend.md`) n'est cochée que si : code complet,
  tests verts, typage OK, zéro `TODO`.
