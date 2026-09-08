"""Hachage du PIN avec Argon2id (adapter du port ``PinHasher``)."""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from flash.domain.identity.pin import Pin


class Argon2PinHasher:
    def __init__(self, hasher: PasswordHasher | None = None) -> None:
        # Paramètres volontairement modestes : le PIN est court et l'espace des valeurs
        # est petit ; c'est le verrouillage après N essais (côté OTP/login) qui protège,
        # pas le coût unitaire du hash.
        self._ph = hasher or PasswordHasher(time_cost=3, memory_cost=64 * 1024, parallelism=2)

    def hash(self, pin: Pin) -> str:
        return self._ph.hash(pin.value)

    def verify(self, pin: Pin, hashed: str) -> bool:
        try:
            self._ph.verify(hashed, pin.value)
        except (VerifyMismatchError, InvalidHashError):
            return False
        return True

    def needs_rehash(self, hashed: str) -> bool:
        try:
            return self._ph.check_needs_rehash(hashed)
        except InvalidHashError:
            return True


__all__ = ["Argon2PinHasher"]
