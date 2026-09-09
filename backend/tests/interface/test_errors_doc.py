"""BE-T5 : garde-fou d'exhaustivité de ``docs/api/errors.md``.

Tout ``code`` renvoyable par l'API (sous-classe de ``DomainError``, entrée de la table
de correspondance HTTP, code synthétisé par la couche interface) **doit** être documenté.
"""

from __future__ import annotations

from pathlib import Path

import flash.interface.app  # noqa: F401  (importe toute l'app → enregistre les sous-classes)
from flash.domain.shared.errors import DomainError
from flash.interface.errors import _STATUS_BY_CODE

_ERRORS_DOC = Path(__file__).resolve().parents[3] / "docs" / "api" / "errors.md"

# Codes produits par la couche interface, hors hiérarchie ``DomainError``.
_INTERFACE_CODES = {
    "UNAUTHENTICATED",
    "INVALID_TOKEN",
    "VALIDATION_ERROR",
    "INTERNAL_ERROR",
    "NOT_FOUND",
    "METHOD_NOT_ALLOWED",
    "BAD_REQUEST",
}


def _all_domain_error_codes() -> set[str]:
    seen: set[str] = set()
    stack: list[type[DomainError]] = [DomainError]
    while stack:
        cls = stack.pop()
        seen.add(cls.code)
        stack.extend(cls.__subclasses__())
    return seen


def _documented_codes() -> str:
    return _ERRORS_DOC.read_text(encoding="utf-8")


def test_errors_doc_exists() -> None:
    assert _ERRORS_DOC.is_file(), f"{_ERRORS_DOC} manquant (BE-T5)"


def test_every_domain_error_code_is_documented() -> None:
    doc = _documented_codes()
    missing = sorted(code for code in _all_domain_error_codes() if f"`{code}`" not in doc)
    assert not missing, f"Codes d'erreur non documentés dans errors.md : {missing}"


def test_every_http_mapped_code_is_documented() -> None:
    doc = _documented_codes()
    missing = sorted(code for code in _STATUS_BY_CODE if f"`{code}`" not in doc)
    assert not missing, f"Codes mappés HTTP non documentés dans errors.md : {missing}"


def test_interface_synthetic_codes_are_documented() -> None:
    doc = _documented_codes()
    missing = sorted(code for code in _INTERFACE_CODES if f"`{code}`" not in doc)
    assert not missing, f"Codes interface non documentés dans errors.md : {missing}"
