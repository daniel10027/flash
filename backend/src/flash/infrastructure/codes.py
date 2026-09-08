"""``PepperedWithdrawalCodes`` — implémentation du port ``WithdrawalCodes``.

Alphabet sans caractères ambigus (pas de 0/O/1/I). Le code n'est jamais stocké en clair :
seule son empreinte SHA-256 salée (poivre = secret applicatif) l'est.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"


class PepperedWithdrawalCodes:
    def __init__(self, pepper: str, *, length: int = 8) -> None:
        self._pepper = pepper.encode()
        self._length = length

    def new_code(self) -> str:
        return "".join(secrets.choice(_ALPHABET) for _ in range(self._length))

    def fingerprint(self, code: str) -> str:
        return hashlib.sha256(self._pepper + code.upper().encode()).hexdigest()

    def matches(self, presented: str, fingerprint: str) -> bool:
        return hmac.compare_digest(self.fingerprint(presented), fingerprint)


__all__ = ["PepperedWithdrawalCodes"]
