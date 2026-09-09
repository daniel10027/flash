# Provisioning du VPS (INFRA-017)

Cible : un VPS Debian 12 / Ubuntu 22.04, 2 vCPU / 4 Go, disque ≥ 40 Go.
Tout tourne en `docker compose` derrière Caddy (TLS automatique).

## 1. Utilisateur & durcissement de base

```sh
# en root
adduser deploy && usermod -aG sudo deploy
rsync --archive --chown=deploy:deploy ~/.ssh /home/deploy   # clé publique de déploiement

# SSH : pas de root, pas de mot de passe
sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin no/; s/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
systemctl restart ssh

# Pare-feu
apt-get update && apt-get install -y ufw fail2ban
ufw default deny incoming && ufw default allow outgoing
ufw allow 22/tcp && ufw allow 80/tcp && ufw allow 443/tcp
ufw enable
systemctl enable --now fail2ban

# Swap (utile avec 4 Go)
fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
```

## 2. Docker

```sh
curl -fsSL https://get.docker.com | sh
usermod -aG docker deploy
# mises à jour de sécurité automatiques
apt-get install -y unattended-upgrades && dpkg-reconfigure -plow unattended-upgrades
```

## 3. Dépôt & secrets

```sh
# en tant que `deploy`
sudo install -d -o deploy -g deploy /opt/flash
git clone https://github.com/daniel10027/flash /opt/flash
cd /opt/flash

# secrets prod : jamais dans le dépôt
sudo install -d -m 750 -o deploy -g deploy /etc/flash
sudo install -m 600 -o deploy -g deploy infra/deploy/.env.prod.example /etc/flash/flash.env
sudo -e /etc/flash/flash.env        # remplir DOMAIN, mots de passe, clés…

# staging : même VPS, projet + env séparés
sudo cp /etc/flash/flash.env /etc/flash/flash-staging.env
sudo -e /etc/flash/flash-staging.env   # COMPOSE_PROJECT_NAME=flash-staging, DOMAIN inchangé
```

## 4. Sauvegardes hors-site

```sh
# clé PUBLIQUE GPG du destinataire des sauvegardes (la privée reste hors VPS)
gpg --import ops-backup-public.asc
# rclone (S3, Backblaze B2, …) si OFFSITE_REMOTE est renseigné
sudo install -m 600 rclone.conf /etc/flash/rclone.conf
```

## 5. DNS

`A`/`AAAA` sur l'IP du VPS pour : `flash.<tld>`, `app.flash.<tld>`,
`api.flash.<tld>` (+ `*.staging.flash.<tld>` pour le staging).

## 6. Premier démarrage

```sh
CMP="docker compose -p flash -f infra/deploy/docker-compose.prod.yml --env-file /etc/flash/flash.env"
$CMP pull
$CMP run --rm migrate
$CMP up -d
$CMP run --rm --entrypoint flash api seed   # jeu de démo, à retirer en vrai prod
curl -fsS https://api.$DOMAIN/health/ready
```

## 7. Secrets GitHub Actions (INFRA-019)

| Secret | Usage |
|---|---|
| `DEPLOY_HOST` / `DEPLOY_USER` | cible SSH (`deploy@vps`) |
| `DEPLOY_SSH_KEY` | clé privée ed25519 dédiée au déploiement |
| `GITHUB_TOKEN` | fourni ; push GHCR |

Variables (repo → Settings → Variables) : `DOMAIN`.
`detect-secrets` en CI + `.gitignore` (`/etc/flash/*` hors dépôt) garantissent
qu'aucun secret n'atterrit dans Git. Rotation : régénérer la clé SSH et les mots
de passe Postgres/admin tous les 6 mois (procédure dans le RUNBOOK).
