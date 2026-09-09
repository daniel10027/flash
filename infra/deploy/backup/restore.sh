#!/bin/sh
# Restauration : déchiffre + décompresse + réinjecte. À lancer DANS le conteneur
# backup (clé privée GPG montée) ou sur une machine outillée.
#
#   ./restore.sh /backups/daily/flash_20260101T020000Z.sql.gz.gpg
#
# Refuse de tourner si la base cible n'est pas vide, sauf FORCE=1.
set -eu

SRC="${1:?usage: restore.sh <fichier .sql.gz.gpg>}"

if [ -f "$SRC.sha256" ]; then
  echo "[restore] vérification d'intégrité…"
  (cd "$(dirname "$SRC")" && sha256sum -c "$(basename "$SRC").sha256")
fi

TABLES=$(psql -tAc "select count(*) from information_schema.tables where table_schema='public'" "$PGDATABASE")
if [ "${TABLES:-0}" -ne 0 ] && [ "${FORCE:-0}" != "1" ]; then
  echo "[restore] la base '$PGDATABASE' contient $TABLES tables. Relance avec FORCE=1 pour écraser." >&2
  exit 1
fi

echo "[restore] $SRC -> $PGDATABASE"
gpg --batch --yes --decrypt "$SRC" \
  | gunzip \
  | psql --set ON_ERROR_STOP=on "$PGDATABASE"

echo "[restore] terminé. Vérifie l'équilibre du ledger : flash run-jobs (reconcile)."
