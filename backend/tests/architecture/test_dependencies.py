"""Garde-fou d'architecture hexagonale (BE-023).

Analyse statiquement les ``import`` de chaque couche et échoue si la règle de dépendance
« vers l'intérieur » est violée. Le domaine ne connaît que la bibliothèque standard et
lui-même ; l'application ne connaît que le domaine ; l'infrastructure et l'interface
peuvent tout câbler mais l'infrastructure ne dépend pas de l'interface.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2] / "src" / "flash"

# Paquets tiers interdits d'import dans le cœur.
_FORBIDDEN_THIRD_PARTY = {
    "flask",
    "sqlalchemy",
    "alembic",
    "redis",
    "pydantic",
    "pydantic_settings",
    "requests",
    "httpx",
    "argon2",
    "jwt",
    "structlog",
    "click",
    "gunicorn",
    "werkzeug",
}


def _module_name(path: Path) -> str:
    rel = path.relative_to(_SRC.parent).with_suffix("")
    return ".".join(rel.parts)


def _imports(path: Path) -> Iterator[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            yield node.module


def _files(layer: str) -> list[Path]:
    return sorted((_SRC / layer).rglob("*.py"))


def _violations(layer: str, forbidden_prefixes: set[str]) -> list[str]:
    problems: list[str] = []
    for file in _files(layer):
        for imported in _imports(file):
            root = imported.split(".")[0]
            hit = root in forbidden_prefixes or any(
                imported == p or imported.startswith(p + ".") for p in forbidden_prefixes
            )
            if hit:
                problems.append(f"{_module_name(file)} importe {imported!r}")
    return problems


class TestDomainIsPure:
    def test_domain_imports_nothing_forbidden(self) -> None:
        forbidden = _FORBIDDEN_THIRD_PARTY | {
            "flash.application",
            "flash.infrastructure",
            "flash.interface",
        }
        assert _violations("domain", forbidden) == []


class TestApplicationDependsOnlyOnDomain:
    def test_application_does_not_import_infra_or_interface(self) -> None:
        forbidden = _FORBIDDEN_THIRD_PARTY | {
            "flash.infrastructure",
            "flash.interface",
        }
        assert _violations("application", forbidden) == []


class TestInfrastructureDoesNotDependOnInterface:
    def test_infrastructure_does_not_import_interface(self) -> None:
        assert _violations("infrastructure", {"flash.interface"}) == []


class TestSanity:
    def test_layers_are_present(self) -> None:
        for layer in ("domain", "application", "infrastructure", "interface"):
            assert _files(layer), f"couche {layer} introuvable"
