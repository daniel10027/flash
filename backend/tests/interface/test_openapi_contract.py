"""BE-T3 : tests de contrat OpenAPI (schemathesis) sur **toutes** les routes.

Le schéma est chargé depuis l'application (test deps en mémoire, aucun service externe).
Pour chaque opération, schemathesis génère des requêtes et vérifie qu'aucune ne provoque
d'erreur serveur (``not_a_server_error``) : c'est le signal de régression de contrat qui
compte ici (500, exception non gérée, réponse illisible). Les 401/403 attendus sur les
routes protégées ne sont pas des échecs.
"""

from __future__ import annotations

import pytest

schemathesis = pytest.importorskip("schemathesis")

from flask import Flask  # noqa: E402

from flash.infrastructure.config import Settings  # noqa: E402
from flash.interface.app import create_app  # noqa: E402
from tests.support.deps import build_test_deps  # noqa: E402
from tests.support.otp import RecordingOtpService  # noqa: E402
from tests.support.repositories import InMemoryUnitOfWork  # noqa: E402
from tests.support.security import build_test_security  # noqa: E402

SECRET = "flash-test-secret-please-ignore-0123456789abcd"


@pytest.fixture
def api_schema() -> object:
    bundle = build_test_security()
    deps = build_test_deps(
        uow=InMemoryUnitOfWork(), otp=RecordingOtpService(), bundle=bundle
    )
    app: Flask = create_app(
        Settings(FLASH_ENV="test", FLASH_SECRET_KEY=SECRET),
        security_bundle=bundle,
        deps=deps,
    )
    return schemathesis.openapi.from_wsgi("/openapi.json", app)


# Les points d'infra (santé, métriques, doc) ne relèvent pas du contrat métier et
# renvoient légitimement 5xx quand la base de test est absente.
schema = schemathesis.pytest.from_fixture("api_schema").exclude(
    path_regex=r"^/(health|metrics|openapi\.json|docs|redoc)"
)


@pytest.mark.contract
@schema.parametrize()
def test_api_contract(case: object) -> None:
    # WSGI → pas de base_url ; check unique : aucune 5xx / exception non gérée.
    case.call_and_validate(checks=[schemathesis.checks.not_a_server_error])
