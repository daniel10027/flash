#!/bin/sh
# Garde les N plus récents de chaque cadence.
set -eu

prune() {
  dir="$1"; keep="$2"
  [ -d "$dir" ] || return 0
  # liste triée du plus ancien au plus récent, supprime tout sauf les `keep` derniers
  ls -1t "$dir"/*.sql.gz.gpg 2>/dev/null | tail -n "+$((keep + 1))" | while read -r f; do
    echo "[prune] rm $f"
    rm -f "$f" "$f.sha256"
  done
}

prune /backups/daily   "$RETENTION_DAILY"
prune /backups/weekly  "$RETENTION_WEEKLY"
prune /backups/monthly "$RETENTION_MONTHLY"
