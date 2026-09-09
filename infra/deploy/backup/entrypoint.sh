#!/bin/sh
set -eu

echo "$BACKUP_CRON /usr/local/bin/backup.sh >> /proc/1/fd/1 2>&1" > /etc/crontabs/root

echo "[backup] cron installé : $BACKUP_CRON"
echo "[backup] rétention j/s/m = $RETENTION_DAILY/$RETENTION_WEEKLY/$RETENTION_MONTHLY"

# Une sauvegarde immédiate au démarrage pour valider la config.
/usr/local/bin/backup.sh || echo "[backup] sauvegarde initiale en échec (voir logs)"

exec crond -f -l 8
