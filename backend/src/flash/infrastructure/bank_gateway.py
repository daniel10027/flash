"""``SandboxBankGateway`` — passerelle bancaire factice, déterministe, sans I/O.

Tout virement est **accepté** et renvoie une référence bancaire dérivée de la référence
Flash. Un connecteur réel (virement instantané / SEPA) le remplacera.
"""

from __future__ import annotations

import hashlib
import hmac

from flash.application.merchants.bank import BankAck


class SandboxBankGateway:
    def __init__(self, *, pepper: str = "sandbox") -> None:
        self._pepper = pepper.encode()

    def transfer(
        self,
        *,
        holder: str,
        iban: str,
        bank_name: str,
        amount_minor: int,
        currency: str,
        reference: str,
    ) -> BankAck:
        digest = hmac.new(self._pepper, f"{iban}:{reference}".encode(), hashlib.sha256)
        return BankAck(accepted=True, bank_reference=f"bank_{digest.hexdigest()[:18]}")


__all__ = ["SandboxBankGateway"]
