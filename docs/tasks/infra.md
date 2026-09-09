# Tâches Infra & CI/CD (`INFRA`)

Cible : dev local en Docker (API + Web + Postgres + Redis + Mailhog), production sur un
**VPS unique** en `docker compose` derrière **Caddy** (TLS auto), déploiement par
**GitHub Actions** en SSH. Notifications gratuites : FCM (push), SMTP (email).

## Local (INFRA-001 → INFRA-006)

- [x] **INFRA-001** · `infra/docker-compose.yml` (dev) : services `api` (Flask + reload),
  `web` (Vite + reload), `db` (postgres:16), `redis`, `mailhog`. Réseaux, volumes,
  `depends_on` avec healthchecks. `.env.example` complet + `.env` git‑ignoré.
- [x] **INFRA-002** · `backend/Dockerfile` multi‑stage (base deps → runtime gunicorn),
  utilisateur non‑root, `HEALTHCHECK`, image finale slim.
- [x] **INFRA-003** · `web/Dockerfile` multi‑stage : `deps` (npm ci) → `dev` (Vite HMR)
  → `build` (bundle) → `runtime` (Caddy `:80` + SPA fallback + en-têtes de sécurité).
  Config runtime `window.__FLASH_CONFIG__` écrite dans `/srv/config.js` par
  `docker-entrypoint.sh` au démarrage ; `HEALTHCHECK` wget. (livré avec `WEB-012`)
- [x] **INFRA-004** · `Makefile` à la racine : `up`/`up-web`/`down`/`down-v`/`logs`/`ps`,
  `migrate`/`makemigration`/`seed`/`reference`/`dbshell`/`shell`, `openapi` (dump +
  `gen:api`), `lint`/`fmt`, `test`/`test-backend`/`test-web`, `build`, `clean`. `make`
  seul affiche l'aide auto-générée.
- [x] **INFRA-005** · `backend/scripts/wait-for-db.sh` (POSIX sh, gère le suffixe
  `+psycopg`, N tentatives) appelé par `dev-entrypoint.sh` → `flash db upgrade` +
  `flash reference seed` + `flash serve --reload`. En prod l'image démarre gunicorn
  directement ; la migration est un job dédié du pipeline (voir `infra/deploy/`).
- [x] **INFRA-006** · `infra/docker-compose.override.yml.example` : lance l'API sous
  `debugpy` (port 5678, attache IDE), surcharge `FLASH_LOG_LEVEL=DEBUG`. Fichier
  `infra/docker-compose.override.yml` git-ignoré, fusionné automatiquement par compose.

## CI (INFRA-007 → INFRA-013)

- [x] **INFRA-007** · `.github/workflows/backend-ci.yml` : ruff, mypy, `pytest --cov`
  (services Postgres + Redis → tests d'intégration & de migrations inclus), seuil
  `fail_under = 90`, diff `docs/api/openapi.json` ↔ `flash openapi dump`, upload
  `coverage.xml`. Cache pip sur `pyproject.toml`, `concurrency` par ref. (livré avec `BE-T1`)
- [x] **INFRA-008** · `.github/workflows/web-ci.yml` : gen:api (diff `schema.d.ts`),
  `npm run lint` (eslint + prettier), `typecheck`, `test:cov` (couverture `features/`
  seuil 80 %), `build`, Playwright (navigateurs en cache `~/.cache/ms-playwright`),
  Lighthouse CI (`npm run lighthouse`). Upload `playwright-report` + `coverage` +
  `.lighthouseci`. Cache npm sur `package-lock.json`, `concurrency` par ref. (livré
  avec `WEB-T1`/`T2`/`T3`)
- [x] **INFRA-009** · `.github/workflows/mobile-ci.yml` : `dart format --set-exit-if-changed`,
  `flutter analyze`, `flutter test --coverage` (widget + provider + golden), `flutter
  build apk --debug --flavor dev` en artefact + `lcov.info`. Cache Flutter, `paths:
  mobile/**` (dormant tant que `mobile/` n'existe pas).
- [x] **INFRA-010** · `.github/workflows/openapi-check.yml` : job `spec-in-sync`
  (`flash openapi dump` ↔ `docs/api/openapi.json`, message d'erreur explicite) + job
  `contract` (`pytest -m contract`, schemathesis, services Postgres + Redis).
- [x] **INFRA-011** · `.github/workflows/images.yml` : matrice `flash-api` (target
  `prod`) / `flash-web` (target `runtime`), push `ghcr.io/<owner>/<image>` taggé
  `sha-<long>` + `latest` (main) + `vX` (tags), cache `type=gha`, `provenance` +
  `sbom` buildx, scan Trivy `HIGH,CRITICAL` `ignore-unfixed` `exit-code 1`, rapport
  SARIF uploadé.
- [x] **INFRA-012** · `.pre-commit-config.yaml` : hooks `pre-commit-hooks` (EOF,
  trailing-whitespace, merge-conflict, check-yaml/json, large-files, line-ending),
  `ruff` + `ruff-format` (backend), `prettier` (web), `hadolint` (Dockerfile),
  `detect-secrets` (`--baseline .secrets.baseline`, révisions Alembic exclues).
  Instructions d'installation en tête de fichier.
- [x] **INFRA-013** · `.github/CODEOWNERS` + `.github/BRANCH_PROTECTION.md` +
  `.github/branch-protection.json` (payload `gh api -X PUT .../branches/main/protection`) :
  4 checks requis, `strict`, 1 review CODEOWNERS avec `dismiss_stale`, historique
  linéaire, `enforce_admins`, pas de force-push ni suppression.

## CD & VPS (INFRA-014 → INFRA-021)

- [ ] **INFRA-014** · `infra/deploy/docker-compose.prod.yml` : `api` (gunicorn, réplicas),
  `web`, `caddy` (reverse proxy + TLS Let's Encrypt), `db` (postgres + volume),
  `redis`, `backup`. Pas de port DB exposé publiquement.
- [ ] **INFRA-015** · `infra/deploy/Caddyfile` : domaines `api.flash.<tld>` et
  `app.flash.<tld>`, en‑têtes de sécurité (HSTS, CSP pour le web, X‑Content‑Type),
  compression, rate‑limit léger.
- [ ] **INFRA-016** · `.github/workflows/deploy.yml` : sur tag `v*` (ou `main` →
  staging), SSH vers le VPS, `docker compose pull && up -d`, migration Alembic en
  job dédié (`alembic upgrade head`) avant bascule, health‑check post‑deploy, rollback
  au tag précédent si échec.
- [ ] **INFRA-017** · Provisioning VPS documenté (`infra/deploy/PROVISION.md`) : user
  non‑root, firewall UFW (22/80/443), fail2ban, Docker + compose plugin, swap,
  déploiement des secrets (`/etc/flash/flash.env`, `chmod 600`).
- [ ] **INFRA-018** · Sauvegardes Postgres : conteneur `backup` (pg_dump chiffré,
  cron, rétention 7/4/6), copie hors‑site (S3‑compatible / rsync), script de
  restauration testé + `RESTORE.md`.
- [ ] **INFRA-019** · Secrets : `GITHUB` secrets pour SSH, registry, FCM, SMTP ;
  rotation documentée ; `detect-secrets` en CI ; aucun secret dans le dépôt.
- [ ] **INFRA-020** · Environnement staging sur le même VPS (préfixe réseau/volumes,
  sous‑domaines `*.staging`) pour valider avant prod.
- [ ] **INFRA-021** · Runbook (`infra/deploy/RUNBOOK.md`) : déployer, rollback,
  restaurer la base, tourner un job, lire les logs, incident solde/ledger.

## Observabilité & sécurité (INFRA-022 → INFRA-024)

- [ ] **INFRA-022** · Logs : JSON structuré → fichier + rotation ; agrégation légère
  (Loki + Grafana en option compose, sinon `docker logs` + Dozzle). Pas de PII.
- [ ] **INFRA-023** · Métriques : `/metrics` Prometheus (API), dashboards Grafana
  (latence p50/p95, taux d'erreur, transferts/min, écart de réconciliation ledger),
  alertes (Alertmanager → email/webhook gratuit).
- [ ] **INFRA-024** · Durcissement : `docker-bench`, images non‑root, FS read‑only où
  possible, `no-new-privileges`, limites CPU/mém, revue OWASP ASVS niveau 2,
  rate‑limit et WAF léger via Caddy, scan de dépendances planifié (Dependabot).
