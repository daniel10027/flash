"""BE-T2 : les migrations Alembic sont testées sur un **Postgres réel**.

- ``upgrade head`` amène le schéma au dernier révision et l'estampille ;
- ``downgrade base`` puis ``upgrade head`` de nouveau (round-trip) : toutes les
  fonctions ``downgrade()`` fonctionnent ;
- le schéma issu des migrations **correspond aux modèles ORM** (``compare_metadata``),
  aux ``server_default`` près — convention du dépôt : ``default=`` Python côté modèle.

Isolé dans une base jetable ``<db>_migrations`` créée sur le même serveur, pour ne pas
toucher la base des autres tests d'intégration.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text

from flash.infrastructure.db import models  # noqa: F401  (peuple Base.metadata)
from flash.infrastructure.db.base import Base

pytestmark = pytest.mark.integration

_BACKEND = Path(__file__).resolve().parents[2]


def _server_base_and_dbname() -> tuple[str, str]:
    url = os.environ.get("FLASH_TEST_DATABASE_URL")
    if not url:
        pytest.skip("FLASH_TEST_DATABASE_URL non défini : tests de migrations ignorés.")
    base, _, dbname = url.rpartition("/")
    return base, dbname


@pytest.fixture
def migration_url() -> Any:
    base, dbname = _server_base_and_dbname()
    scratch = f"{dbname}_migrations"
    admin = create_engine(
        f"{base}/postgres", isolation_level="AUTOCOMMIT", future=True
    )
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{scratch}" WITH (FORCE)'))
        conn.execute(text(f'CREATE DATABASE "{scratch}"'))
    try:
        yield f"{base}/{scratch}"
    finally:
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{scratch}" WITH (FORCE)'))
        admin.dispose()


@pytest.fixture
def alembic_cfg(migration_url: str, monkeypatch: pytest.MonkeyPatch) -> Any:
    # ``alembic/env.py`` force ``sqlalchemy.url`` = ``get_settings().database_url``.
    monkeypatch.setenv("DATABASE_URL", migration_url)
    from flash.infrastructure.config import get_settings

    get_settings.cache_clear()
    cfg = Config(str(_BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(_BACKEND / "alembic"))
    cfg.set_main_option("sqlalchemy.url", migration_url)
    try:
        yield cfg
    finally:
        get_settings.cache_clear()


def _table_names(url: str) -> set[str]:
    engine = create_engine(url, future=True)
    try:
        return set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def _structural_diffs(url: str) -> list[Any]:
    """Diffs modèle ↔ base, en ignorant les seuls ``modify_default`` (server_default)."""
    engine = create_engine(url, future=True)
    try:
        with engine.connect() as conn:
            ctx = MigrationContext.configure(
                conn, opts={"compare_type": True}
            )
            raw = compare_metadata(ctx, Base.metadata)
    finally:
        engine.dispose()

    kept: list[Any] = []
    for diff in raw:
        entries = diff if isinstance(diff, list) else [diff]
        if all(
            isinstance(e, tuple) and e and e[0] == "modify_default" for e in entries
        ):
            continue
        kept.append(diff)
    return kept


def test_upgrade_head_stamps_latest_revision(
    alembic_cfg: Config, migration_url: str
) -> None:
    command.upgrade(alembic_cfg, "head")
    head = ScriptDirectory.from_config(alembic_cfg).get_current_head()
    engine = create_engine(migration_url, future=True)
    try:
        with engine.connect() as conn:
            stamped = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    finally:
        engine.dispose()
    assert stamped == head
    assert "merchant_sub_accounts" in _table_names(migration_url)
    assert "pricing_rules" in _table_names(migration_url)


def test_full_roundtrip_upgrade_downgrade_upgrade(
    alembic_cfg: Config, migration_url: str
) -> None:
    command.upgrade(alembic_cfg, "head")
    assert len(_table_names(migration_url)) > 20

    command.downgrade(alembic_cfg, "base")
    remaining = _table_names(migration_url) - {"alembic_version"}
    assert remaining == set(), f"tables non supprimées par les downgrade() : {remaining}"

    command.upgrade(alembic_cfg, "head")  # ré-application complète
    assert "users" in _table_names(migration_url)


def test_schema_from_migrations_matches_orm_models(
    alembic_cfg: Config, migration_url: str
) -> None:
    command.upgrade(alembic_cfg, "head")
    diffs = _structural_diffs(migration_url)
    assert diffs == [], f"le schéma migré diverge des modèles ORM : {diffs}"
