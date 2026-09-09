# Test de charge (BE-T6)

`locustfile.py` mesure le chemin chaud **transfert P2P** sous concurrence.

## Cible SLO

| Métrique | Objectif |
|---|---|
| p95 `POST /v1/transfers` | **< 300 ms** |
| Taux d'erreur global | < 1 % |
| Charge | 200 utilisateurs simultanés, montée 20/s, 2 min |

Le run `locust --headless` **sort en code ≠ 0** si un de ces seuils est dépassé
(`events.quitting`), ce qui permet de le brancher en CI/nightly.

## Prérequis

1. API Flash déployée et joignable (`FLASH_BASE_URL`).
2. `flash seed` exécuté sur la cible (crée `+2250700000101` / `+2250700000102`
   approvisionnés).
3. `FLASH_SECRET_KEY` identique à celui de l'API et `DATABASE_URL` accessible depuis la
   machine de test — le script résout les `user_id` des comptes de démo et signe des
   jetons d'accès (l'authentification n'est pas l'objet de la mesure).

## Lancer

```sh
cd backend
export FLASH_BASE_URL=http://localhost:8000
export FLASH_SECRET_KEY=...                       # == celui de l'API
export DATABASE_URL=postgresql+psycopg://flash:flash@localhost:5433/flash

# headless, avec garde-fou SLO + export CSV
locust -f loadtest/locustfile.py --headless \
       -u 200 -r 20 -t 2m --host "$FLASH_BASE_URL" \
       --csv loadtest/report

# ou UI interactive
locust -f loadtest/locustfile.py --host "$FLASH_BASE_URL"
```

Rapports : `loadtest/report_stats.csv`, `loadtest/report_failures.csv`.

## Scénario

Chaque utilisateur virtuel alterne : `POST /v1/transfers` (poids 10), `GET /v1/wallets`
(3), `GET /v1/statement` (1). Les transferts de 100 unités mineures font l'aller-retour
entre les deux comptes de démo ; chaque requête a sa propre `Idempotency-Key`.
