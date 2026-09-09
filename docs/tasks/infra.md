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
- [ ] **INFRA-003** · `web/Dockerfile` multi‑stage (build Vite → serveur statique Caddy),
  config runtime injectée (`window.__FLASH_CONFIG__`).
- [ ] **INFRA-004** · `Makefile` / `justfile` : `up`, `down`, `logs`, `migrate`, `seed`,
  `test`, `lint`, `fmt`, `openapi`, `shell`.
- [ ] **INFRA-005** · Script `scripts/wait-for-db.sh` + entrypoint API (applique les
  migrations Alembic au démarrage en dev, pas en prod).
- [ ] **INFRA-006** · `docker-compose.override.yml` d'exemple pour brancher un débogueur
  et monter le code en volume.

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
- [ ] **INFRA-009** · `.github/workflows/mobile-ci.yml` : `flutter analyze`, `flutter
  test`, golden, build APK debug en artefact.
- [ ] **INFRA-010** · `.github/workflows/openapi-check.yml` : régénère `openapi.json` et
  échoue si divergence avec le fichier commité ; schemathesis contre l'API de test.
- [ ] **INFRA-011** · Build & push images : `ghcr.io/<org>/flash-api` et `flash-web`,
  taggées par `sha` + `latest` sur `main`. SBOM + scan Trivy (échec sur CVE haute).
- [ ] **INFRA-012** · `pre-commit` (ruff, black/ruff-format, end-of-file, detect-secrets,
  hadolint) + doc d'installation.
- [ ] **INFRA-013** · Protection de branche `main` : CI verte obligatoire, 1 review,
  pas de push direct.

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
