#!/usr/bin/env sh
# Entrypoint de développement : attend la base, applique les migrations, seed le
# référentiel + (en dev) le jeu de démo complet, puis lance l'API avec
# rechargement automatique.
#
# En PRODUCTION, l'image ne passe PAS par ce script : la migration Alembic est un
# job dédié du pipeline de déploiement (voir infra/deploy/), et le conteneur `api`
# démarre directement gunicorn.
set -eu

DIR=$(dirname "$0")

sh "$DIR/wait-for-db.sh"

echo "[flash] migrations Alembic…"
flash db upgrade

echo "[flash] référentiel pays / opérateurs…"
flash reference seed

if [ "${FLASH_DEV_SEED:-0}" = "1" ]; then
  echo "[flash] jeu de démo (tous les profils)…"
  flash seed || echo "[flash] seed ignoré (déjà en place ou erreur non bloquante)"
fi

echo "[flash] démarrage de l'API sur :8000"
exec flash serve --host 0.0.0.0 --port 8000
