# Restauration de la base Postgres

## Pré-requis

- La **clé privée GPG** correspondant à `BACKUP_GPG_RECIPIENT` (jamais sur le VPS
  en clair ; importée temporairement au moment de la restauration).
- Un fichier de sauvegarde `*.sql.gz.gpg` (+ son `.sha256`), local ou tiré du
  remote hors-site : `rclone copy <remote>/daily/<fichier> ./`.

## Procédure (incident total)

```sh
cd /opt/flash                     # dossier de déploiement
ENV=/etc/flash/flash.env
CMP="docker compose -f infra/deploy/docker-compose.prod.yml --env-file $ENV"

# 1. arrêter l'API (garde db + backup up)
$CMP stop api web caddy

# 2. importer la clé privée dans le conteneur backup
gpg --export-secret-keys <KEYID> | $CMP exec -T backup gpg --batch --import

# 3. recréer une base vide
$CMP exec -T db psql -U "$POSTGRES_USER" -c \
  "DROP DATABASE IF EXISTS $POSTGRES_DB; CREATE DATABASE $POSTGRES_DB OWNER $POSTGRES_USER;"

# 4. restaurer
$CMP exec -T backup sh -lc \
  'FORCE=1 /usr/local/bin/restore.sh /backups/daily/<FICHIER>.sql.gz.gpg'

# 5. re-appliquer les migrations éventuellement plus récentes que la sauvegarde
$CMP run --rm migrate

# 6. contrôle d'intégrité comptable AVANT de rouvrir le service
#    `flash run-jobs` inclut la réconciliation des soldes et sort 1 si écart.
$CMP run --rm --entrypoint "flash" api run-jobs   # doit sortir 0

# 7. redémarrer
$CMP up -d api web caddy
$CMP exec -T backup rm -f /tmp/*   # purge la clé importée
```

## Test de restauration (à planifier trimestriellement)

Restaurer la dernière sauvegarde dans une base jetable `flash_restore_test` sur
un environnement isolé, lancer `flash run-jobs` (réconciliation incluse), vérifier
le nombre d'utilisateurs / le total des soldes, puis supprimer la base.
