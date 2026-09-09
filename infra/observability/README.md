# Observabilité (INFRA-022/023)

Pile optionnelle, superposée à la prod, sous le profil `observability` :

```sh
CMP="docker compose \
  -f infra/deploy/docker-compose.prod.yml \
  -f infra/observability/docker-compose.observability.yml \
  --env-file /etc/flash/flash.env"

$CMP --profile observability up -d
```

| Composant | Rôle |
|---|---|
| **Prometheus** | scrape `api:8000/metrics` (découverte DNS des réplicas), règles d'alerte `prometheus/alerts.yml` |
| **Alertmanager** | route les alertes vers e-mail (SMTP existant) ou webhook |
| **Loki + Promtail** | agrège les logs de tous les conteneurs (JSON structlog → label `level`), rétention 14 j |
| **Grafana** | datasources + dashboard « Flash — API » provisionnés (`grafana/`) |

Métriques exposées par l'API : `flash_http_requests_total{method,endpoint,status}`,
`flash_http_request_duration_seconds` (histogramme), `flash_http_requests_in_progress`.

Alertes : API down, taux 5xx > 5 %, p95 > 750 ms, saturation. L'**écart de
réconciliation du ledger** est porté par le code retour de `flash run-jobs`
(cron) — à surveiller via l'ordonnanceur ou un textfile collector (stub commenté
dans `alerts.yml`).

Accès Grafana : ajouter un vhost `metrics.$DOMAIN` protégé (basicauth Caddy) ou
tunnel SSH `ssh -L 3000:localhost:3000 deploy@vps` puis
`docker compose ... port grafana 3000`. Ne jamais exposer Grafana/Prometheus sans
authentification.
