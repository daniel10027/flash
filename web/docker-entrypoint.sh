#!/bin/sh
# WEB-011 — génère /srv/config.js à partir des variables d'environnement de l'image,
# puis démarre Caddy. index.html charge <script src="/config.js"> avant le bundle.
set -eu

cat > /srv/config.js <<EOF
window.__FLASH_CONFIG__ = {
  API_BASE_URL: "${FLASH_API_BASE_URL:-}",
  ENV: "${FLASH_ENV:-production}",
  SENTRY_DSN: "${FLASH_SENTRY_DSN:-}"
};
EOF

echo "[flash-web] config.js généré (API_BASE_URL=${FLASH_API_BASE_URL:-<vide>}, ENV=${FLASH_ENV:-production})"
exec caddy run --config /etc/caddy/Caddyfile --adapter caddyfile
