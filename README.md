# Flash

**Plateforme de monnaie électronique (mobile money)** — transferts entre
particuliers, paiements marchands par QR, dépôts / retraits cash en agence,
comptes opérateurs, coffre, épargne, carte virtuelle. Multi‑pays (zone UEMOA /
XOF au lancement). Frais de transfert : **0,8 %**. Ledger en **partie double**.

> **Statut : toutes les phases livrées.**
> Backend **84/84** · Web **49/49** · Mobile **47/47** · Infra & CI/CD **24/24** ·
> Design **10/10** · Fondations **6/6** (+ transverses `BE-T1…T6`, `WEB-T1…T3`,
> `MOB-T1…T3`). Détail : [`ROADMAP.md`](./ROADMAP.md).

---

## Démarrer — tout en une commande

```sh
cp .env.example .env
docker compose -f infra/docker-compose.yml up --build
```

Lance PostgreSQL, Redis, Mailhog, l'**API** (migrations + référentiel +
**seed complet de tous les profils** au démarrage) et le **SPA web**.

| | URL |
|---|---|
| Application web | http://localhost:5173 |
| Back-office | http://localhost:5173/admin |
| API + doc interactive | http://localhost:8000 · http://localhost:8000/docs |
| Boîte mail (Mailhog) | http://localhost:8025 |

Comptes de démonstration, rôles et scénario pas à pas :
**[`docs/GUIDE.md`](./docs/GUIDE.md)**. En résumé : clients
`+2250700000101…104`, agent `+2250700000199`, marchand `+2250700000188`, **code
secret `1397`** ; back-office `X-Admin-Key` = `dev-admin-key` /
`dev-compliance-key` / `dev-finance-key`. Les OTP sont dans les logs de l'API
(`docker compose … logs -f api`).

Application mobile : voir [`mobile/README.md`](./mobile/README.md)
(`flutter run --flavor dev -t lib/main_dev.dart --dart-define=API_BASE_URL=http://10.0.2.2:8000`).

---

## Ce que fait Flash

| Domaine | Fonctionnalités |
|---|---|
| **Client** | inscription + OTP, connexion (biométrie mobile), code secret oublié, solde masquable, **envoyer** (aperçu frais 0,8 %) + annuler, **demander de l'argent**, **payer un marchand** (scan QR), recevoir, **retrait / dépôt cash**, compte opérateur, historique + **reçu partageable**, **coffre**, **épargne** (intérêts), **carte virtuelle** (révéler PAN/CVV 30 s), 5 numéros, **KYC** par paliers, notifications (**SSE** + push FCM), appareils connectés, changer le code secret |
| **Agent** | float plafonné, **dépôt client**, confirmation de retrait, top-up / withdraw float, **commissions**, hiérarchie (agent parent / sous-agents), journal + export CSV |
| **Marchand** | enrôlement, **KYB**, **clés d'API** `/merchant/v1`, QR statique / dynamique, **sous-comptes** (caisses / employés), frais négociés par canal, **webhooks signés** (HMAC), remboursement, relevés & règlements bancaires, affiche imprimable |
| **Back-office** | 4 rôles par clé (`X-Admin-Key`) — **Support** (recherche, gel, contre-passation forcée, notes, tickets, **file KYC** + aperçu des pièces), **Conformité** (alertes **AML**, scan par seuils, blocage préventif, **export STR**, **audit** + contrôle d'intégrité de la chaîne), **Finance** (balance générale, journal, exports mensuels, règlements, **grille tarifaire & plafonds éditables**), **Admin** |
| **Jobs** | expiration d'opérations, **réconciliation** des soldes, épargne programmée + intérêts, règlements marchands, dispatch des webhooks, commissions agent |

---

## Architecture

Monorepo, **architecture hexagonale** (le domaine ne dépend d'aucune techno).

| Dossier | Contenu | Stack |
|---|---|---|
| [`backend/`](./backend) | API + cœur métier + jobs + CLI | Python 3.12, Flask, SQLAlchemy 2, Alembic, PostgreSQL, Redis, Pydantic v2 |
| [`web/`](./web) | App web (client + espace agent + back-office) | React 18, Vite, TypeScript strict, TanStack Query, React Router, Zustand |
| [`mobile/`](./mobile) | App mobile client | Flutter 3, Dart, Riverpod, go_router, dio |
| [`infra/`](./infra) | Docker Compose dev, CI/CD, déploiement VPS, observabilité | Docker, GitHub Actions, Caddy, Prometheus / Loki / Grafana |
| [`design/`](./design) | Charte, logo, tokens, iconographie, modèle de reçu | SVG, JSON tokens |
| [`docs/`](./docs) | Architecture, modèle métier, spec API, guides | Markdown, OpenAPI 3.1 |

**Principes non négociables** — aucun `TODO`/`FIXME` de complaisance dans le code
livré ; toute écriture d'argent produit des postings **équilibrés** (jamais de
mutation de solde hors ledger) ; toute opération monétaire accepte une **clé
d'idempotence** ; frais / limites / paliers KYC / devise / opérateurs pilotés par
**configuration**, jamais en dur dans le métier.

---

## Tous les documents

### Suivi & décisions
- [`ROADMAP.md`](./ROADMAP.md) — avancement (source de vérité), narratif par phase
- Lots de tâches (IDs stables, cases à cocher) :
  [backend](./docs/tasks/backend.md) ·
  [web](./docs/tasks/frontend-web.md) ·
  [mobile](./docs/tasks/mobile.md) ·
  [infra & CI/CD](./docs/tasks/infra.md) ·
  [design](./docs/tasks/design.md)
- Décisions d'architecture (ADR) :
  [0001 — stack](./docs/decisions/0001-stack.md) ·
  [0002 — hexagonal](./docs/decisions/0002-hexagonal.md) ·
  [0003 — ledger partie double](./docs/decisions/0003-ledger-partie-double.md) ·
  [0004 — multi-pays](./docs/decisions/0004-multi-pays.md)

### Utilisation & conception
- **[`docs/GUIDE.md`](./docs/GUIDE.md) — guide d'utilisation : tous les rôles, toutes les fonctionnalités, comptes de démo, scénario**
- [`docs/architecture.md`](./docs/architecture.md) — vue d'ensemble technique, flux clés
- [`docs/domain-model.md`](./docs/domain-model.md) — agrégats, invariants, événements
- [`design/BRAND.md`](./design/BRAND.md) · [`design/COMPONENTS.md`](./design/COMPONENTS.md) · [`design/README.md`](./design/README.md)

### API
- [`docs/api/openapi.json`](./docs/api/openapi.json) — spécification OpenAPI 3.1 (Swagger UI : `/docs`, ReDoc : `/redoc`)
- [`docs/api/errors.md`](./docs/api/errors.md) — catalogue exhaustif des codes d'erreur

### Exploitation
- [`backend/README.md`](./backend/README.md) · [`web/README.md`](./web/README.md) · [`mobile/README.md`](./mobile/README.md)
- [`infra/deploy/PROVISION.md`](./infra/deploy/PROVISION.md) — provisioning du VPS
- [`infra/deploy/RUNBOOK.md`](./infra/deploy/RUNBOOK.md) — déployer, rollback, incident solde/ledger
- [`infra/deploy/backup/RESTORE.md`](./infra/deploy/backup/RESTORE.md) — restauration de la base
- [`infra/observability/README.md`](./infra/observability/README.md) — métriques, logs, alertes
- [`docs/security/HARDENING.md`](./docs/security/HARDENING.md) — durcissement (OWASP ASVS, Trivy, Dependabot)
- [`.github/BRANCH_PROTECTION.md`](./.github/BRANCH_PROTECTION.md) — règles de la branche `main`

---

## Développement

```sh
make help            # tous les raccourcis
make up-web          # pile complète (idem docker compose ci-dessus)
make migrate seed    # migrations + jeu de démo dans le conteneur
make lint fmt test   # backend (ruff/mypy/pytest) + web (eslint/prettier/vitest)
make openapi         # régénère docs/api/openapi.json + le client TS du web
```

`pre-commit` : `pipx install pre-commit && pre-commit install`
(voir [`.pre-commit-config.yaml`](./.pre-commit-config.yaml)).

### Tests & CI

| Lot | Local | CI (GitHub Actions) |
|---|---|---|
| Backend | `cd backend && pytest` (couverture ≥ 90 %, 100 % domaine + application) | `backend-ci.yml` (ruff, mypy, pytest + Postgres/Redis), `openapi-check.yml` (diff + schemathesis) |
| Web | `cd web && npm test && npm run e2e` | `web-ci.yml` (lint, typecheck, `test:cov` seuil 80 % sur `features/`, build, Playwright, **Lighthouse** ≥ 90) |
| Mobile | `cd mobile && flutter test` (widget + provider + golden) | `mobile-ci.yml` (`dart format`, `flutter analyze`, tests + coverage, build APK) |
| Images | — | `images.yml` (GHCR `flash-api` / `flash-web`, SBOM + provenance, scan **Trivy** bloquant) |
| Déploiement | — | `deploy.yml` (tag `v*` → prod, `main` → staging, migration avant bascule, health-check, rollback auto) |

---

## Sécurité & conformité — à lire avant tout usage réel

Le produit est **complet côté fonctionnel**, mais opérer une monnaie électronique
exige : agrément **BCEAO**, intégrations **bancaires / opérateurs / réseau carte**
de production (aujourd'hui des adaptateurs *sandbox*), audits **PCI-DSS** et
sécurité, et une campagne de tests de charge sur l'infrastructure cible. Les
connecteurs externes sont des ports isolés (`OperatorGateway`, `CardIssuer`,
`BankGateway`) à remplacer par des implémentations agréées.
