#!/usr/bin/env sh
# Entrypoint de développement : attend la base, applique les migrations, lance l'API
# avec rechargement automatique.
set -eu

echo "[flash] attente de PostgreSQL…"
python - <<'PY'
import os, time, sys
import psycopg

url = os.environ["DATABASE_URL"].replace("+psycopg", "")
for attempt in range(60):
    try:
        with psycopg.connect(url, connect_timeout=2):
            break
    except Exception as exc:  # noqa: BLE001
        print(f"  ... ({attempt + 1}/60) {exc.__class__.__name__}")
        time.sleep(1)
else:
    sys.exit("PostgreSQL indisponible")
print("[flash] PostgreSQL prêt")
PY

echo "[flash] migrations Alembic…"
flash db upgrade

echo "[flash] démarrage de l'API sur :8000"
exec flash serve --host 0.0.0.0 --port 8000
