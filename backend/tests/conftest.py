"""Fixtures partagées.

Les tests d'intégration (marqueur ``integration``) ont besoin d'un PostgreSQL. Fournir
son URL via ``FLASH_TEST_DATABASE_URL`` (sinon ces tests sont ignorés). Le schéma est
créé une fois pour la session ; chaque test tourne dans une transaction annulée à la fin
(les ``commit`` applicatifs deviennent des savepoints).
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from sqlalchemy import Connection, Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from flash.infrastructure.db import models  # noqa: F401  (peuple Base.metadata)
from flash.infrastructure.db.base import Base

_TEST_DB_URL = os.environ.get("FLASH_TEST_DATABASE_URL")


@pytest.fixture(scope="session")
def db_engine() -> Iterator[Engine]:
    if not _TEST_DB_URL:
        pytest.skip("FLASH_TEST_DATABASE_URL non défini : tests d'intégration ignorés.")
    engine = create_engine(_TEST_DB_URL, future=True)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    try:
        yield engine
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture
def db_connection(db_engine: Engine) -> Iterator[Connection]:
    connection = db_engine.connect()
    transaction = connection.begin()
    try:
        yield connection
    finally:
        transaction.rollback()
        connection.close()


@pytest.fixture
def session_factory(db_connection: Connection) -> sessionmaker[Session]:
    return sessionmaker(
        bind=db_connection,
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
        future=True,
    )


@pytest.fixture
def db_session(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
