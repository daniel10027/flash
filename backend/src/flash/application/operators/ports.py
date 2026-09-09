"""Port ``OperatorGateway`` — frontière avec les opérateurs mobile money.

Les appels ``payout`` / ``collect`` ne font qu'**initier** l'opération (mode asynchrone) :
ils renvoient ``accepted`` + une référence externe. Le statut final arrive par webhook
(``POST /v1/operators/{op}/callbacks``). L'implémentation réelle (Orange/MTN/Moov via un
agrégateur) est remplaçable ; ``SandboxOperatorGateway`` sert en dev et en test.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class GatewayAck:
    accepted: bool
    external_ref: str
    reason: str | None = None


@runtime_checkable
class OperatorGateway(Protocol):
    def payout(
        self,
        *,
        operator: str,
        msisdn: str,
        amount_minor: int,
        currency: str,
        reference: str,
    ) -> GatewayAck: ...

    def collect(
        self,
        *,
        operator: str,
        msisdn: str,
        amount_minor: int,
        currency: str,
        reference: str,
    ) -> GatewayAck: ...


__all__ = ["GatewayAck", "OperatorGateway"]
