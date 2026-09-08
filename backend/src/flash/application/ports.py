"""Ports propres à la couche application (au-delà des ports transverses du domaine)."""

from __future__ import annotations

from enum import StrEnum
from typing import Protocol, runtime_checkable

from flash.domain.shared.identifiers import Msisdn


class OtpPurpose(StrEnum):
    ACTIVATION = "ACTIVATION"
    ADD_PHONE_NUMBER = "ADD_PHONE_NUMBER"
    LOGIN_DEVICE = "LOGIN_DEVICE"
    PIN_RESET = "PIN_RESET"


@runtime_checkable
class OtpService(Protocol):
    """Émission et vérification de codes à usage unique envoyés par SMS.

    ``issue`` génère un code, le stocke (haché, avec TTL) et le fait envoyer.
    ``verify`` lève ``OtpInvalid`` (code faux/expiré) ou ``OtpTooManyAttempts`` ; en cas
    de succès, le code est consommé.
    """

    def issue(self, msisdn: Msisdn, purpose: OtpPurpose) -> None: ...

    def verify(self, msisdn: Msisdn, purpose: OtpPurpose, code: str) -> None: ...


__all__ = ["OtpPurpose", "OtpService"]
