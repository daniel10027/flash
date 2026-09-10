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
- [x] **INFRA-004** · `Makefile` à la racine : `dev` (pile + flutter run IP LAN), `up`/`up-d`/`down`/`down-v`/`logs`/`ps`,
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

- [x] **INFRA-014** · `infra/deploy/docker-compose.prod.yml` : `caddy` (80/443, seul
  exposé), `web`, `api` (image GHCR, `deploy.replicas`, `GUNICORN_CMD_ARGS`,
  `read_only` + tmpfs), `db` + `redis` (réseau interne, healthchecks), `backup`,
  service one-shot `migrate` (profil `tools`). Ancres `x-restart`/`x-logging`
  (json-file 10 Mo×5)/`x-hardening` (`no-new-privileges`, `cap_drop: ALL`), `mem_limit`
  par service.
- [x] **INFRA-015** · `infra/deploy/caddy/` : `Dockerfile` (build Caddy 2.8 + module
  `caddy-ratelimit`) + `Caddyfile` — vhosts `app.$DOMAIN` / `api.$DOMAIN`, snippet
  `security_headers` (HSTS preload, `X-Content-Type-Options`, `Referrer-Policy`,
  `X-Frame-Options`, `Permissions-Policy`), CSP dédiée au bundle Vite, `encode zstd
  gzip`, `rate_limit` par IP (300/min app, 600/min API), `request_body max_size 8MB`,
  `reverse_proxy` avec `health_uri`. Racine → redirection vers l'app.
- [x] **INFRA-016** · `.github/workflows/deploy.yml` : tag `v*` → production, push
  `main` → staging (projet + env-file séparés). SSH (clé dédiée), `checkout` du SHA,
  mémorise le tag courant, `compose pull` → `run --rm migrate` → `up -d`. Health-check
  `GET /health/ready` (30×5 s) ; **rollback** automatique vers le tag précédent si KO.
- [x] **INFRA-017** · `infra/deploy/PROVISION.md` : user `deploy` non-root, SSH durci,
  UFW 22/80/443 + fail2ban, swap 2 Go, install Docker + `unattended-upgrades`, clone
  `/opt/flash`, secrets `/etc/flash/*.env` (0600), clé publique GPG + rclone,
  DNS, premier démarrage, table des secrets GitHub Actions. `.env.prod.example` fourni.
- [x] **INFRA-018** · `infra/deploy/backup/` : image Alpine (`postgresql16-client`,
  `gnupg`, `rclone`) + `crond`. `backup.sh` : `pg_dump | gzip -9 | gpg --encrypt`
  vers `daily/weekly/monthly` selon le jour, `sha256`, `prune.sh` (rétention 7/4/6),
  `rclone sync` hors-site si `OFFSITE_REMOTE`. `restore.sh` (vérif sha256, refuse une
  base non vide sans `FORCE=1`) + `RESTORE.md` (procédure incident + test trimestriel).
- [x] **INFRA-019** · Secrets hors dépôt (`/etc/flash/*.env`, `.gitignore`),
  `detect-secrets` en pré-commit (baseline auditée), table `DEPLOY_HOST/USER/SSH_KEY`
  + var `DOMAIN` dans `PROVISION.md`, procédure de rotation semestrielle (SSH, mdp
  Postgres, clés admin, `FLASH_SECRET_KEY`) dans le `RUNBOOK`.
- [x] **INFRA-020** · Staging = même VPS, `COMPOSE_PROJECT_NAME=flash-staging`
  (réseaux/volumes préfixés) + `/etc/flash/flash-staging.env` + sous-domaines
  `*.staging.$DOMAIN`. `deploy.yml` cible staging à chaque push `main`, production
  sur tag `v*`.
- [x] **INFRA-021** · `infra/deploy/RUNBOOK.md` : déployer (auto/manuel), rollback
  (+ `db downgrade`), restaurer (renvoi `RESTORE.md`), lancer `run-jobs`, lire les
  logs, **procédure incident solde/ledger** (gel → `run-jobs` → audit → contre-passation,
  jamais de SQL direct), rotation des secrets.

## Observabilité & sécurité (INFRA-022 → INFRA-024)

- [x] **INFRA-022** · Logs applicatifs JSON (structlog, sans PII) ; en prod
  `logging: json-file` borné (10 Mo × 5). Agrégation optionnelle
  `infra/observability/` : Loki + Promtail (découverte Docker, label `level`,
  rétention 14 j), profil `observability`.
- [x] **INFRA-023** · `GET /metrics` déjà exposé (BE-T4). `infra/observability/` :
  Prometheus (scrape DNS des réplicas `api`, `prometheus/alerts.yml` : API down,
  5xx > 5 %, p95 > 750 ms, saturation), Alertmanager (e-mail/webhook), Grafana
  provisionné (dashboard « Flash — API » : req/s, taux d'erreur, p50/p95/p99,
  transferts/min, logs Loki). Écart de réconciliation ledger = code retour de
  `flash run-jobs` (cron), stub d'alerte commenté.
- [x] **INFRA-024** · `docs/security/HARDENING.md` : `no-new-privileges` + `cap_drop:
  ALL` + `read_only`/tmpfs (api) + `mem_limit` + non-root dans `docker-compose.prod.yml` ;
  rate-limit + limite de corps + en-têtes + CSP via Caddy ; SBOM/provenance + scan
  Trivy bloquant en CI ; `.github/dependabot.yml` (pip/npm/actions/docker hebdo) ;
  commande `docker-bench` et checklist OWASP ASVS L2 documentées.
