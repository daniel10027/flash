"""``SandboxOperatorGateway`` — passerelle opérateur factice, déterministe, sans I/O.

Toute initiation est **acceptée** et renvoie une référence externe dérivée de la
référence Flash. Le statut final est fourni séparément via le webhook
``POST /v1/operators/{op}/callbacks`` (piloté par les tests / un simulateur).
"""

from __future__ import annotations

import hashlib
import hmac

from flash.application.operators.ports import GatewayAck


class SandboxOperatorGateway:
    def __init__(self, *, pepper: str = "sandbox") -> None:
        self._pepper = pepper.encode()

    def _ack(self, *, kind: str, reference: str) -> GatewayAck:
        digest = hmac.new(self._pepper, f"{kind}:{reference}".encode(), hashlib.sha256)
        return GatewayAck(accepted=True, external_ref=f"op_{digest.hexdigest()[:20]}")

    def payout(
        self, *, operator: str, msisdn: str, amount_minor: int, currency: str, reference: str
    ) -> GatewayAck:
        return self._ack(kind="payout", reference=reference)

    def collect(
        self, *, operator: str, msisdn: str, amount_minor: int, currency: str, reference: str
    ) -> GatewayAck:
        return self._ack(kind="collect", reference=reference)


__all__ = ["SandboxOperatorGateway"]
