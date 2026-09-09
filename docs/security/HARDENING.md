# Durcissement (INFRA-024)

## Conteneurs

Appliqué dans `infra/deploy/docker-compose.prod.yml` :

| Mesure | Où |
|---|---|
| `no-new-privileges:true` | tous les services (ancre `x-hardening` + `security_opt`) |
| `cap_drop: [ALL]` | `api`, `web`, `redis`, `backup` |
| `read_only: true` + `tmpfs: /tmp` | `api` |
| Utilisateur non-root | image `flash-api` (`USER flash`, uid 10001), `caddy`, `postgres`, `redis` |
| `mem_limit` par service | tous |
| Pas de port hôte pour `db` / `redis` | réseau interne uniquement ; seul `caddy` publie 80/443 |
| Logs bornés | `json-file`, `max-size 10m`, `max-file 5` (pas de PII dans les logs applicatifs — structlog) |
| Secrets hors image et hors dépôt | `/etc/flash/*.env` (0600), `.gitignore`, `detect-secrets` en CI |

`web` reste inscriptible (`/srv/config.js` généré au démarrage) mais sans
capacités ni privilèges.

## Réseau / bord

- TLS Let's Encrypt automatique (Caddy), HSTS `preload`.
- En-têtes : `X-Content-Type-Options`, `Referrer-Policy`, `X-Frame-Options: DENY`,
  `Permissions-Policy`, CSP stricte pour le SPA (`script-src 'self'`).
- Rate-limit de bord par IP (`caddy-ratelimit`) + limite de taille de corps 8 Mo,
  en complément du rate-limit métier Redis (login, OTP, `change-pin`, reset…).
- UFW 22/80/443 + fail2ban sur le VPS (voir `infra/deploy/PROVISION.md`).

## Chaîne d'approvisionnement

- Images buildées en CI avec `provenance` + `sbom` (buildx).
- Scan **Trivy** `HIGH,CRITICAL` bloquant (`exit-code 1`, `ignore-unfixed`) sur
  chaque image poussée — `.github/workflows/images.yml`.
- **Dependabot** hebdo : pip, npm, github-actions, docker (`.github/dependabot.yml`).
- `detect-secrets` en pré-commit + baseline auditée.

## Vérifications périodiques

- **docker-bench-security** sur le VPS (trimestriel) :
  `docker run --rm --net host --pid host --cap-add audit_control \
   -v /var/lib:/var/lib:ro -v /var/run/docker.sock:/var/run/docker.sock:ro \
   -v /etc:/etc:ro docker/docker-bench-security`
- **Revue OWASP ASVS niveau 2** — points déjà couverts : auth (Argon2id + PIN,
  JWT court + refresh rotatif + révocation Redis), gestion de session (déconnexion
  à distance, reset PIN révoque tout), contrôle d'accès (RBAC back-office par clé,
  403 fail-closed), journalisation d'audit chaînée et vérifiable, idempotence des
  écritures, ledger en partie double (jamais de mutation destructive), validation
  d'entrée Pydantic, secrets hors code. À refaire à chaque évolution majeure de
  l'authentification ou du modèle de permissions.
- Restauration de sauvegarde testée (voir `infra/deploy/backup/RESTORE.md`).
