"""Port ``CardIssuer`` — la frontière avec l'émetteur de cartes (réseau / processeur).

L'implémentation réelle (Visa/Mastercard via un processeur) est remplaçable ; en
développement et en test on utilise ``SandboxCardIssuer``. Le domaine ne voit jamais le
vrai PAN : l'émetteur rend un ``pan_token`` opaque et les 4 derniers chiffres.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class IssuedCard:
    pan_token: str
    last4: str
    network: str
    expiry_month: int
    expiry_year: int


@dataclass(frozen=True, slots=True)
class CardSecret:
    """Données sensibles révélées ponctuellement au titulaire (jamais journalisées)."""

    pan: str
    cvv: str
    expiry_month: int
    expiry_year: int


@runtime_checkable
class CardIssuer(Protocol):
    def issue(self, *, card_id: str, holder_ref: str, network: str = "") -> IssuedCard: ...

    def freeze(self, pan_token: str) -> None: ...

    def unfreeze(self, pan_token: str) -> None: ...

    def close(self, pan_token: str) -> None: ...

    def reveal(self, pan_token: str) -> CardSecret: ...


__all__ = ["CardIssuer", "CardSecret", "IssuedCard"]
