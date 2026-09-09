#!/bin/sh
# Dump compressé + chiffré GPG (clé publique du destinataire), puis élagage et
# copie hors-site optionnelle.
set -eu

TS=$(date -u +%Y%m%dT%H%M%SZ)
DOW=$(date -u +%u)   # 1..7 (lundi..dimanche)
DOM=$(date -u +%d)   # 01..31

OUT_DIR=/backups/daily
[ "$DOW" = "7" ] && OUT_DIR=/backups/weekly
[ "$DOM" = "01" ] && OUT_DIR=/backups/monthly
mkdir -p "$OUT_DIR"

FILE="$OUT_DIR/${PGDATABASE}_${TS}.sql.gz.gpg"

echo "[backup] dump -> $FILE"
pg_dump --no-owner --no-privileges "$PGDATABASE" \
  | gzip -9 \
  | gpg --batch --yes --trust-model always \
        --encrypt --recipient "$BACKUP_GPG_RECIPIENT" \
        --output "$FILE"

# Empreinte pour vérif d'intégrité.
sha256sum "$FILE" > "$FILE.sha256"

/usr/local/bin/prune.sh

if [ -n "${OFFSITE_REMOTE:-}" ]; then
  echo "[backup] copie hors-site -> $OFFSITE_REMOTE"
  rclone sync /backups "$OFFSITE_REMOTE" --checksum --transfers 2
fi

echo "[backup] OK $TS"
