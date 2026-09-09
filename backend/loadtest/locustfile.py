"""Test de charge Flash (BE-T6) — transferts P2P concurrents.

Objectif : p95 < 300 ms sur ``POST /v1/transfers`` à 200 utilisateurs simultanés
(environnement de staging, 2 workers gunicorn, Postgres + Redis locaux).

Prérequis :
- une API Flash joignable (``FLASH_BASE_URL``, défaut ``http://localhost:8000``) ;
- le jeu de démo chargé : ``flash seed`` (crée ``+2250700000101`` / ``+2250700000102``
  avec du solde) ;
- ``FLASH_SECRET_KEY`` **identique** à celui de l'API et ``DATABASE_URL`` accessible
  (le script résout les ``user_id`` des comptes de démo et signe des jetons d'accès
  courts — l'auth n'est pas l'objet de la mesure).

Lancement :

    cd backend
    FLASH_BASE_URL=http://localhost:8000 \
    FLASH_SECRET_KEY=... DATABASE_URL=postgresql+psycopg://flash:flash@localhost:5433/flash \
    locust -f loadtest/locustfile.py --headless -u 200 -r 20 -t 2m \
           --host "$FLASH_BASE_URL" --csv loadtest/report

Le run échoue (code ≠ 0) si le p95 dépasse la cible ou si le taux d'erreur > 1 %.
"""

from __future__ import annotations

import itertools
import os
import uuid

from locust import HttpUser, between, events, task
from sqlalchemy import create_engine, text

from flash.infrastructure.security.jwt_codec import JwtTokenCodec

_SECRET = os.environ["FLASH_SECRET_KEY"]
_DB_URL = os.environ.get(
    "DATABASE_URL", "postgresql+psycopg://flash:flash@localhost:5433/flash"
)
_DEMO_PHONES = ("+2250700000101", "+2250700000102")

_P95_TARGET_MS = 300
_MAX_ERROR_RATIO = 0.01


def _mint_access_token(user_id: str) -> str:
    """Signe un jeton d'accès (mêmes claims que ``TokenService``)."""
    return JwtTokenCodec(_SECRET).encode(
        {"sub": user_id, "did": "loadtest", "type": "access", "jti": uuid.uuid4().hex},
        ttl_seconds=3600,
    )


def _resolve_demo_users() -> list[tuple[str, str]]:
    """(user_id, phone) des comptes de démo, lus en base."""
    engine = create_engine(_DB_URL, future=True)
    rows: list[tuple[str, str]] = []
    try:
        with engine.connect() as conn:
            for phone in _DEMO_PHONES:
                uid = conn.execute(
                    text(
                        "SELECT user_id FROM phone_numbers WHERE msisdn = :m LIMIT 1"
                    ),
                    {"m": phone},
                ).scalar()
                if uid is not None:
                    rows.append((str(uid), phone))
    finally:
        engine.dispose()
    if len(rows) < 2:
        raise RuntimeError(
            "Comptes de démo introuvables — lancez `flash seed` sur la cible."
        )
    return rows


_USERS: list[tuple[str, str]] = []
_RING = itertools.count()


def _pick_user() -> tuple[str, str]:
    if not _USERS:
        _USERS.extend(_resolve_demo_users())
    return _USERS[next(_RING) % len(_USERS)]


class TransferUser(HttpUser):
    """Envoie en boucle de petits transferts vers l'autre compte de démo."""

    wait_time = between(0.1, 0.5)

    def on_start(self) -> None:
        user_id, _phone = _pick_user()
        idx = _USERS.index((user_id, _phone))
        self._user_id = user_id
        self._recipient_phone = _USERS[(idx + 1) % len(_USERS)][1]
        self._headers = {"Authorization": f"Bearer {_mint_access_token(self._user_id)}"}

    @task(10)
    def send_transfer(self) -> None:
        self.client.post(
            "/v1/transfers",
            json={"recipient_phone_number": self._recipient_phone, "amount_minor": 100},
            headers={**self._headers, "Idempotency-Key": uuid.uuid4().hex},
            name="POST /v1/transfers",
        )

    @task(3)
    def read_wallets(self) -> None:
        self.client.get("/v1/wallets", headers=self._headers, name="GET /v1/wallets")

    @task(1)
    def read_statement(self) -> None:
        self.client.get(
            "/v1/statement?limit=20", headers=self._headers, name="GET /v1/statement"
        )


@events.quitting.add_listener
def _enforce_slo(environment: object, **_kw: object) -> None:
    stats = environment.stats  # type: ignore[attr-defined]
    total = stats.total
    p95 = total.get_response_time_percentile(0.95)
    error_ratio = (total.num_failures / total.num_requests) if total.num_requests else 1.0

    failed = False
    if p95 > _P95_TARGET_MS:
        print(f"SLO KO : p95 {p95:.0f} ms > cible {_P95_TARGET_MS} ms")
        failed = True
    if error_ratio > _MAX_ERROR_RATIO:
        print(f"SLO KO : taux d'erreur {error_ratio:.2%} > {_MAX_ERROR_RATIO:.0%}")
        failed = True
    if failed:
        environment.process_exit_code = 1  # type: ignore[attr-defined]
    else:
        print(f"SLO OK : p95 {p95:.0f} ms, erreurs {error_ratio:.2%}")
