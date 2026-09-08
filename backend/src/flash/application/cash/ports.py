"""Ports propres aux opérations cash."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class WithdrawalCodes(Protocol):
    """Fabrique et vérification des codes de retrait à usage unique.

    - ``new_code`` : code lisible destiné au client.
    - ``fingerprint`` : empreinte non réversible stockée sur l'ordre.
    - ``matches`` : comparaison en temps constant du code présenté avec l'empreinte.
    """

    def new_code(self) -> str: ...

    def fingerprint(self, code: str) -> str: ...

    def matches(self, presented: str, fingerprint: str) -> bool: ...


__all__ = ["WithdrawalCodes"]
