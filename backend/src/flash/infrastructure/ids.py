"""Génération d'identifiants UUIDv7 (triables par le temps).

Implémentation locale conforme au brouillon RFC 9562 : 48 bits de timestamp
millisecondes, version 7, variant RFC 4122, le reste aléatoire. Évite une dépendance
tierce pour une primitive aussi simple.
"""

from __future__ import annotations

import os
import time
from uuid import UUID

from flash.domain.shared.identifiers import EntityId


def uuid7(*, when_ms: int | None = None) -> UUID:
    ts = when_ms if when_ms is not None else time.time_ns() // 1_000_000
    rand = os.urandom(10)

    value = (ts & 0xFFFFFFFFFFFF) << 80
    value |= 0x7 << 76  # version 7
    value |= (rand[0] & 0x0F) << 72
    value |= rand[1] << 64
    value |= 0b10 << 62  # variant RFC 4122
    value |= (rand[2] & 0x3F) << 56
    for i in range(3, 10):
        value |= rand[i] << (8 * (9 - i))
    return UUID(int=value)


class Uuid7Generator:
    """Adapter du port ``IdGenerator``."""

    def new_id(self) -> EntityId:
        return EntityId(str(uuid7()))


__all__ = ["Uuid7Generator", "uuid7"]
