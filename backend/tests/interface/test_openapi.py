"""Tests de la génération OpenAPI et des pages de doc (BE-024)."""

from __future__ import annotations

import pytest
from flask import Flask, jsonify
from flask.wrappers import Response

from flash.infrastructure.config import Settings
from flash.interface.app import create_app
from flash.interface.openapi import build_spec, document
from tests.support.security import build_test_security

SECRET = "flash-test-secret-please-ignore-0123456789abcd"


@pytest.fixture
def app() -> Flask:
    application = create_app(
        Settings(FLASH_ENV="test", FLASH_SECRET_KEY=SECRET),
        security_bundle=build_test_security(),
    )

    @application.post("/v1/demo/transfers")
    @document(
        summary="Créer un transfert",
        tags=["demo"],
        request_schema={"type": "object", "properties": {"amount": {"type": "integer"}}},
        response_schema={"type": "object", "properties": {"id": {"type": "string"}}},
        status_code=201,
        secured=True,
        idempotent=True,
    )
    def _demo_transfer() -> Response:
        return jsonify(id="t-1")

    return application


class TestSpec:
    def test_spec_is_openapi_31_with_core_metadata(self, app: Flask) -> None:
        spec = build_spec(app)
        assert spec["openapi"] == "3.1.0"
        assert spec["info"]["title"] == "Flash API"
        assert spec["servers"][0]["url"]
        assert "Error" in spec["components"]["schemas"]
        assert "bearerAuth" in spec["components"]["securitySchemes"]

    def test_health_routes_are_documented_minimally(self, app: Flask) -> None:
        spec = build_spec(app)
        assert "/health" in spec["paths"]
        assert "get" in spec["paths"]["/health"]

    def test_documented_operation_is_fully_described(self, app: Flask) -> None:
        op = build_spec(app)["paths"]["/v1/demo/transfers"]["post"]
        assert op["summary"] == "Créer un transfert"
        assert op["tags"] == ["demo"]
        assert op["security"] == [{"bearerAuth": []}]
        assert op["requestBody"]["required"] is True
        assert "201" in op["responses"]
        assert "4XX" in op["responses"]
        assert op["parameters"][0]["name"] == "Idempotency-Key"

    def test_flask_converters_become_openapi_path_params(self, app: Flask) -> None:
        @app.get("/v1/demo/items/<int:item_id>")
        def _item(item_id: int) -> Response:
            return jsonify(id=item_id)

        assert "/v1/demo/items/{item_id}" in build_spec(app)["paths"]


class TestDocsEndpoints:
    def test_openapi_json_served(self, app: Flask) -> None:
        resp = app.test_client().get("/openapi.json")
        assert resp.status_code == 200
        assert resp.get_json()["openapi"] == "3.1.0"

    def test_swagger_and_redoc_pages_served(self, app: Flask) -> None:
        assert app.test_client().get("/docs").status_code == 200
        assert app.test_client().get("/redoc").status_code == 200
