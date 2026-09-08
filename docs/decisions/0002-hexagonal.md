# ADR 0002 — Architecture hexagonale (ports & adapters)

**Statut :** accepté · **Date :** 2026-09-08

## Contexte
Domaine financier avec règles fortes (frais, limites, KYC, partie double). Ces règles
doivent être testables vite, sûres, et indépendantes du framework HTTP et de la base.

## Décision
Quatre couches, règle de dépendance **vers l'intérieur** :

1. `domain/` — entités, VO, agrégats, invariants, services de domaine, **ports**
   (interfaces), erreurs métier. **Aucun import externe** (ni Flask, ni SQLAlchemy, ni
   Redis, ni requests, ni pydantic).
2. `application/` — use cases (1 classe = 1 cas), orchestration, Unit of Work,
   idempotence, publication d'événements. Dépend de `domain/` uniquement.
3. `infrastructure/` — adapters : repos SQLAlchemy, Alembic, Redis, FCM, SMTP,
   passerelles opérateurs/carte/banque (sandbox), horloge, UUID, crypto. Implémente les
   ports de `domain/`.
4. `interface/` — Flask (blueprints, schémas pydantic, mappers DTO↔commande, OpenAPI,
   sécurité JWT, rate‑limit), CLI, jobs planifiés. Dépend de `application/` et
   `infrastructure/` (câblage).

Le **câblage** (choix des adapters concrets) se fait dans `interface/container.py` /
`create_app`, jamais dans le domaine ou les use cases.

## Règles vérifiées automatiquement
- Test d'architecture (`tests/architecture/`) : échec si `domain/` importe un paquet
  interdit, ou si `application/` importe `infrastructure/` ou `interface/`.
- `mypy` strict sur `domain/` et `application/`.
- Revue : toute nouvelle dépendance externe dans le domaine est un défaut de conception.

## Conséquences
- Tests de domaine sans base ni réseau → millisecondes, couverture ≥ 90 %.
- Changer Postgres, le fournisseur push, ou même Flask n'impacte pas le cœur.
- Coût : un peu plus de code (mappers ORM↔domaine, DTO↔commande). Assumé.
