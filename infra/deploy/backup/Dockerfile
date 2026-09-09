# INFRA-018 — conteneur de sauvegarde Postgres : pg_dump chiffré GPG, cron,
# rétention 7/4/6, copie hors-site optionnelle via rclone.
FROM alpine:3.20

RUN apk add --no-cache postgresql16-client gnupg rclone tzdata

COPY backup.sh /usr/local/bin/backup.sh
COPY prune.sh /usr/local/bin/prune.sh
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/*.sh

ENV RETENTION_DAILY=7 \
    RETENTION_WEEKLY=4 \
    RETENTION_MONTHLY=6 \
    BACKUP_CRON="17 2 * * *"

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
