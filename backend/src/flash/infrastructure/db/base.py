"""Déclaration de base SQLAlchemy et convention de nommage des contraintes.

Les modèles ORM vivent uniquement dans cette couche : ils ne sont **jamais** manipulés
par ``domain`` ni ``application``. La conversion se fait dans ``mappers.py``.
"""

from __future__ import annotations

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.types import DateTime

# Convention explicite : indispensable pour qu'Alembic génère des noms de contrainte stables.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

# Tous les horodatages persistés sont en ``timestamptz`` (timezone-aware, UTC).
TZDateTime = DateTime(timezone=True)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


__all__ = ["NAMING_CONVENTION", "Base", "TZDateTime"]
