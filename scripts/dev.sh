#!/usr/bin/env sh
# Flash — démarre TOUTE la pile de dev en une commande :
#   * docker compose (db, redis, mailhog, API + seed, web) ;
#   * puis, sur l'hôte, `flutter run` de l'app mobile pointée sur l'IP LAN de
#     cette machine — pour qu'un téléphone / émulateur du même réseau atteigne
#     le backend.
#
# Usage :
#   ./scripts/dev.sh                 # pile + mobile
#   SKIP_MOBILE=1 ./scripts/dev.sh   # pile seule
#   ./scripts/dev.sh -d <device>     # cible un device flutter précis
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"

COMPOSE="docker compose -f infra/docker-compose.yml"

# ---------------------------------------------------------------- .env
if [ ! -f .env ]; then
  echo "[dev] .env absent -> copie de .env.example"
  cp .env.example .env
fi

# ---------------------------------------------------------------- IP LAN
detect_lan_ip() {
  # macOS : interface par défaut puis ipconfig
  if command -v route >/dev/null 2>&1 && command -v ipconfig >/dev/null 2>&1; then
    _if=$(route -n get 8.8.8.8 2>/dev/null | awk '/interface:/{print $2}')
    [ -n "${_if:-}" ] && ipconfig getifaddr "$_if" 2>/dev/null && return 0
  fi
  # Linux
  if command -v ip >/dev/null 2>&1; then
    ip route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="src"){print $(i+1); exit}}' && return 0
  fi
  if command -v hostname >/dev/null 2>&1; then
    hostname -I 2>/dev/null | awk '{print $1}' && return 0
  fi
  echo "127.0.0.1"
}

LAN_IP=${FLASH_LAN_IP:-$(detect_lan_ip)}
[ -n "$LAN_IP" ] || LAN_IP="127.0.0.1"
API_URL="http://$LAN_IP:8000"

# ---------------------------------------------------------------- stack
echo "[dev] démarrage de la pile Docker…"
$COMPOSE up -d --build

echo "[dev] attente de l'API ($API_URL/health)…"
i=0
until curl -fsS "http://localhost:8000/health" >/dev/null 2>&1; do
  i=$((i + 1))
  [ "$i" -gt 90 ] && { echo "[dev] l'API ne répond pas — voir '$COMPOSE logs api'"; exit 1; }
  sleep 2
done

cat <<EOF

  ┌───────────────────────────────────────────────────────────────
  │  Web      http://$LAN_IP:5173        (aussi http://localhost:5173)
  │  API      $API_URL         doc : $API_URL/docs
  │  Mailhog  http://$LAN_IP:8025
  │  Back-office  http://$LAN_IP:5173/admin   (X-Admin-Key : dev-admin-key)
  │
  │  Comptes de démo + guide complet : docs/GUIDE.md
  │  OTP : $COMPOSE logs -f api | grep -i otp
  └───────────────────────────────────────────────────────────────

EOF

# ---------------------------------------------------------------- mobile
if [ "${SKIP_MOBILE:-0}" = "1" ]; then
  echo "[dev] SKIP_MOBILE=1 — pile prête, mobile non lancé."
  echo "[dev] Suivi des logs : $COMPOSE logs -f"
  exit 0
fi

if ! command -v flutter >/dev/null 2>&1; then
  echo "[dev] Flutter introuvable — pile prête. Lancer l'app plus tard avec :"
  echo "      cd mobile && flutter run -t lib/main_dev.dart \\"
  echo "        --dart-define=FLAVOR=dev --dart-define=API_BASE_URL=$API_URL"
  exit 0
fi

cd mobile
flutter pub get >/dev/null

# Android définit des productFlavors -> `--flavor` obligatoire.
# iOS n'a pas de schémas de flavor -> `--flavor` échoue : on l'omet quand la
# seule cible mobile branchée est un appareil iOS.
FLAVOR_FLAG="--flavor dev"
if flutter devices 2>/dev/null | grep -qi "• ios" \
  && ! flutter devices 2>/dev/null | grep -qi "• android"; then
  FLAVOR_FLAG=""
  echo "[dev] cible iOS détectée -> lancement sans --flavor"
fi

echo "[dev] flutter run  (API_BASE_URL=$API_URL)…"
# shellcheck disable=SC2086
exec flutter run $FLAVOR_FLAG -t lib/main_dev.dart \
  --dart-define=FLAVOR=dev \
  --dart-define=API_BASE_URL="$API_URL" \
  "$@"
