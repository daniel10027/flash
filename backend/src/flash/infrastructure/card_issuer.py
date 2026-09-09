"""``SandboxCardIssuer`` — émetteur de cartes factice, déterministe, sans I/O.

Le ``pan_token`` est dérivé du couple (card_id, titulaire) par HMAC ; le PAN et le CVV
sont re-dérivés du token à la volée (``reveal``), donc rien de sensible n'est stocké.
``freeze`` / ``unfreeze`` / ``close`` sont des no-op : l'état de la carte vit dans
l'agrégat ``Card``.
"""

from __future__ import annotations

import hashlib
import hmac
from datetime import UTC, datetime

from flash.application.card.ports import CardSecret, IssuedCard

_KNOWN_NETWORKS = ("VISA", "MASTERCARD")


def _digits(seed: bytes, length: int) -> str:
    out: list[str] = []
    counter = 0
    while len(out) < length:
        block = hashlib.sha256(seed + counter.to_bytes(4, "big")).digest()
        out.extend(str(b % 10) for b in block)
        counter += 1
    return "".join(out[:length])


class SandboxCardIssuer:
    def __init__(
        self, *, pepper: str, default_network: str = "VISA", validity_years: int = 3
    ) -> None:
        self._pepper = pepper.encode()
        self._default_network = (
            default_network if default_network in _KNOWN_NETWORKS else "VISA"
        )
        self._validity_years = validity_years

    # ------------------------------------------------------------------ émission
    def issue(self, *, card_id: str, holder_ref: str, network: str = "") -> IssuedCard:
        digest = hmac.new(self._pepper, f"{card_id}:{holder_ref}".encode(), hashlib.sha256)
        pan_token = "tok_" + digest.hexdigest()[:24]
        pan = self._pan(pan_token)
        now = datetime.now(UTC)
        return IssuedCard(
            pan_token=pan_token,
            last4=pan[-4:],
            network=network if network in _KNOWN_NETWORKS else self._default_network,
            expiry_month=now.month,
            expiry_year=now.year + self._validity_years,
        )

    def freeze(self, pan_token: str) -> None:
        return None

    def unfreeze(self, pan_token: str) -> None:
        return None

    def close(self, pan_token: str) -> None:
        return None

    # ------------------------------------------------------------------ révélation
    def reveal(self, pan_token: str) -> CardSecret:
        now = datetime.now(UTC)
        return CardSecret(
            pan=self._pan(pan_token),
            cvv=_digits(self._pepper + b"cvv" + pan_token.encode(), 3),
            expiry_month=now.month,
            expiry_year=now.year + self._validity_years,
        )

    # ------------------------------------------------------------------ interne
    def _pan(self, pan_token: str) -> str:
        return _digits(self._pepper + b"pan" + pan_token.encode(), 16)


__all__ = ["SandboxCardIssuer"]
