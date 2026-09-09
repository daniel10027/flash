#!/usr/bin/env sh
# INFRA-005 — attend que PostgreSQL accepte les connexions avant de continuer.
# Usage : wait-for-db.sh [URL] [TENTATIVES]
#   URL        défaut $DATABASE_URL (format SQLAlchemy `postgresql+psycopg://…` accepté)
#   TENTATIVES défaut 60 (1 s entre chaque)
set -eu

URL="${1:-${DATABASE_URL:-}}"
TRIES="${2:-60}"

if [ -z "$URL" ]; then
  echo "wait-for-db: DATABASE_URL manquant" >&2
  exit 2
fi

# psycopg ne connaît pas le suffixe de driver SQLAlchemy.
DSN=$(printf '%s' "$URL" | sed 's/+psycopg//; s/+asyncpg//')

i=1
while [ "$i" -le "$TRIES" ]; do
  if python - "$DSN" <<'PY' 2>/dev/null
import sys
import psycopg

with psycopg.connect(sys.argv[1], connect_timeout=2):
    pass
PY
  then
    echo "[wait-for-db] PostgreSQL prêt (tentative $i)"
    exit 0
  fi
  echo "[wait-for-db] indisponible ($i/$TRIES)…"
  i=$((i + 1))
  sleep 1
done

echo "[wait-for-db] PostgreSQL toujours indisponible après $TRIES tentatives" >&2
exit 1
