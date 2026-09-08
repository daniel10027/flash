# Flash

Plateforme de monnaie électronique (mobile money) — transferts, paiements marchands,
dépôts / retraits cash en agence, coffre, épargne, carte. Multi‑pays (zone UEMOA / XOF
au lancement). Frais de transfert : **0,8 %**.

## Composants

| Dossier    | Contenu | Stack |
|------------|---------|-------|
| `backend/` | API + cœur métier | Python 3.12, Flask, SQLAlchemy 2, PostgreSQL, architecture hexagonale |
| `web/`     | Application web client + espace agent | React 18, Vite, TypeScript |
| `mobile/`  | Application mobile client | Flutter 3, Dart |
| `infra/`   | Docker, docker‑compose, CI/CD, déploiement VPS | Docker, GitHub Actions, Caddy |
| `design/`  | Charte graphique, logo, tokens | SVG, JSON tokens |
| `docs/`    | Architecture, modèle de domaine, spec API, **map de développement** | Markdown, OpenAPI |

## Où en est le projet

**La source de vérité de l'avancement est [`ROADMAP.md`](./ROADMAP.md)** et les fichiers
détaillés dans [`docs/tasks/`](./docs/tasks/). Chaque tâche a une case à cocher et un
identifiant stable (`BE-001`, `WEB-014`, `MOB-007`, `INFRA-003`, `DSN-002`).

Règle de travail : au début de chaque session, lire `ROADMAP.md`, repérer la prochaine
tâche non cochée dans l'ordre, l'implémenter complètement (code + tests + doc), cocher,
mettre à jour la date de « Dernière mise à jour » en tête de `ROADMAP.md`.

## Démarrage local (après la tâche INFRA‑001)

```bash
cp .env.example .env
docker compose -f infra/docker-compose.yml up --build
# API   : http://localhost:8000
# Web   : http://localhost:5173
# Doc   : http://localhost:8000/docs
# Mails : http://localhost:8025  (Mailhog)
```

## Principes non négociables

- **Aucun `TODO` / `FIXME` / `pass` de complaisance** dans le code livré. Une tâche est
  soit non commencée (non cochée), soit terminée et fonctionnelle.
- **Ledger en partie double** : toute écriture d'argent produit des postings équilibrés
  (somme = 0). Aucune mutation de solde hors ledger.
- **Idempotence** : toute opération monétaire accepte une clé d'idempotence.
- **Le domaine ne dépend de rien** : ni Flask, ni SQLAlchemy, ni réseau. Seulement des
  ports (interfaces). Les technos vivent dans `infrastructure/` et `interface/`.
- **Multi‑pays par configuration** : frais, limites, paliers KYC, devise, opérateurs —
  jamais en dur dans le code métier.
