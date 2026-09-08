"""Faux service OTP pour les tests."""

from __future__ import annotations

from flash.application.ports import OtpPurpose
from flash.domain.shared.errors import OtpInvalid
from flash.domain.shared.identifiers import Msisdn


class RecordingOtpService:
    """Mémorise les codes émis ; ``verify`` accepte le dernier code émis pour le couple
    (numéro, motif), ou lève ``OtpInvalid``."""

    def __init__(self) -> None:
        self.issued: list[tuple[str, OtpPurpose]] = []
        self._codes: dict[tuple[str, OtpPurpose], str] = {}

    def issue(self, msisdn: Msisdn, purpose: OtpPurpose) -> None:
        self.issued.append((msisdn.value, purpose))
        self._codes[(msisdn.value, purpose)] = "000000"

    def verify(self, msisdn: Msisdn, purpose: OtpPurpose, code: str) -> None:
        expected = self._codes.get((msisdn.value, purpose))
        if expected is None or code != expected:
            raise OtpInvalid()
        del self._codes[(msisdn.value, purpose)]

    def last_purpose_for(self, msisdn: str) -> OtpPurpose | None:
        for number, purpose in reversed(self.issued):
            if number == msisdn:
                return purpose
        return None


__all__ = ["RecordingOtpService"]
