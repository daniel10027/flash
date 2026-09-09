"""Blueprint ``reference`` (BE-061) — référentiel public pays / opérateurs."""

from __future__ import annotations

from flask import Blueprint, Response, jsonify

from flash.application.reference.queries import GetCountry, ListCountries
from flash.interface.container import deps
from flash.interface.openapi import document

bp = Blueprint("reference", __name__, url_prefix="/v1/reference")

_OPERATOR_SCHEMA = {
    "type": "object",
    "properties": {
        "code": {"type": "string"},
        "name": {"type": "string"},
        "msisdn_prefixes": {"type": "array", "items": {"type": "string"}},
        "active": {"type": "boolean"},
    },
}
_COUNTRY_SCHEMA = {
    "type": "object",
    "properties": {
        "code": {"type": "string"},
        "name": {"type": "string"},
        "currency": {"type": "string"},
        "dialing_code": {"type": "string"},
        "timezone": {"type": "string"},
        "operators": {"type": "array", "items": _OPERATOR_SCHEMA},
    },
}


@bp.get("/countries")
@document(
    summary="Pays pris en charge et leurs opérateurs mobile money",
    tags=["reference"],
    secured=False,
    response_schema=_COUNTRY_SCHEMA,
)
def list_countries() -> tuple[Response, int]:
    views = ListCountries(directory=deps().reference).execute()
    return jsonify({"countries": [v.to_dict() for v in views]}), 200


@bp.get("/countries/<code>")
@document(
    summary="Détail d'un pays du référentiel",
    tags=["reference"],
    secured=False,
    response_schema=_COUNTRY_SCHEMA,
)
def get_country(code: str) -> tuple[Response, int]:
    view = GetCountry(directory=deps().reference).execute(code)
    return jsonify(view.to_dict()), 200


__all__ = ["bp"]
