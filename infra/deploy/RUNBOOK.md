# Runbook exploitation (INFRA-021)

`CMP` ci-dessous = raccourci sur le VPS :

```sh
cd /opt/flash
CMP="docker compose -p flash -f infra/deploy/docker-compose.prod.yml --env-file /etc/flash/flash.env"
# staging : -p flash-staging --env-file /etc/flash/flash-staging.env
```

## Déployer

Automatique : tag `vX.Y.Z` sur `main` → workflow `deploy` (staging à chaque push
sur `main`). Manuel :

```sh
git -C /opt/flash fetch --tags && git -C /opt/flash checkout vX.Y.Z
export IMAGE_TAG=vX.Y.Z
$CMP pull && $CMP run --rm migrate && $CMP up -d
curl -fsS https://api.$DOMAIN/health/ready
```

## Rollback

```sh
export IMAGE_TAG=<tag précédent>     # visible dans GHCR ou l'historique des déploiements
$CMP pull && $CMP up -d
# si la migration doit être défaite :
$CMP run --rm --entrypoint "flash" api db downgrade -1
```

## Restaurer la base

Voir [`backup/RESTORE.md`](backup/RESTORE.md). En résumé : `stop api`, importer la
clé privée GPG, `restore.sh`, `run --rm migrate`, `flash run-jobs` (réconciliation
verte), `up -d`.

## Lancer un job planifié à la main

```sh
$CMP run --rm --entrypoint "flash" api run-jobs      # expiration + réconciliation + règlements…
$CMP logs -f api | grep -E "reconcile|écart"
```
`run-jobs` sort **1** si la réconciliation détecte un écart de solde.

## Lire les logs

```sh
$CMP logs -f --tail=200 api        # ou web / caddy / db / backup
docker logs --since 1h $($CMP ps -q api | head -1)
```
Logs JSON (`json-file`, 10 Mo × 5). Agrégation optionnelle : voir
`infra/observability/`.

## Incident « solde / ledger »

1. **Geler** les écritures suspectes : `flash` back-office → geler le compte
   (`POST /v1/admin/accounts/<id>/freeze`).
2. `flash run-jobs` → identifie les portefeuilles dont
   `available + reserved + vaulted + saved` ≠ solde recalculé du ledger.
3. Inspecter : `GET /v1/admin/audit?actor=<id>` + journal comptable
   `GET /v1/admin/reports/journal?start=…&end=…`.
4. Correction uniquement par **contre-passation** (`/v1/admin/transactions/force-reversal`),
   jamais de `DELETE` ni d'`UPDATE` direct en base. Chaque action est tracée
   (registre d'audit chaîné, `GET /v1/admin/audit/verify`).
5. Post-mortem : snapshot base (`backup.sh`), ticket, note interne sur le compte.

## Rotation des secrets (semestriel)

- Clé SSH de déploiement : générer, mettre à jour `DEPLOY_SSH_KEY`, retirer
  l'ancienne de `~deploy/.ssh/authorized_keys`.
- `POSTGRES_PASSWORD` : `ALTER USER flash PASSWORD …`, mettre à jour
  `/etc/flash/*.env`, `$CMP up -d api`.
- `ADMIN_API_KEY` / `ADMIN_API_KEYS` : éditer l'env, `up -d api`, prévenir le
  back-office.
- `FLASH_SECRET_KEY` : rotation = invalidation de tous les refresh tokens
  (déconnexion générale) — planifier une fenêtre.
