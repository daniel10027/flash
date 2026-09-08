"""Code secret (PIN) et port de hachage.

Le ``Pin`` porte la valeur en clair **de façon transitoire** (le temps d'une requête).
Il n'est jamais journalisé ni sérialisé : seul son empreinte (via ``PinHasher``) est
persistée.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise
from typing import Protocol, runtime_checkable

_MIN_LEN = 4
_MAX_LEN = 6


@dataclass(frozen=True, slots=True)
class Pin:
    """Suite de 4 à 6 chiffres, hors combinaisons triviales."""

    value: str

    def __post_init__(self) -> None:
        if not self.value.isdigit() or not _MIN_LEN <= len(self.value) <= _MAX_LEN:
            raise ValueError(f"Le PIN doit contenir {_MIN_LEN} à {_MAX_LEN} chiffres.")
        if self._is_trivial(self.value):
            raise ValueError("PIN trop simple : évitez les répétitions et les suites.")

    @staticmethod
    def _is_trivial(value: str) -> bool:
        if len(set(value)) == 1:  # 0000, 111111…
            return True
        digits = [int(c) for c in value]
        ascending = all(b - a == 1 for a, b in pairwise(digits))
        descending = all(a - b == 1 for a, b in pairwise(digits))
        return ascending or descending

    def __repr__(self) -> str:
        return f"Pin(len={len(self.value)}, value='***')"

    def __str__(self) -> str:
        return "***"


@runtime_checkable
class PinHasher(Protocol):
    """Hachage à sens unique du PIN (Argon2id en production)."""

    def hash(self, pin: Pin) -> str: ...

    def verify(self, pin: Pin, hashed: str) -> bool: ...

    def needs_rehash(self, hashed: str) -> bool:
        """Vrai si l'empreinte a été produite avec des paramètres obsolètes."""
        ...


__all__ = ["Pin", "PinHasher"]
