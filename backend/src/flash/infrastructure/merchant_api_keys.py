"""``Sha256MerchantApiKeyVault`` — implémentation du port ``MerchantApiKeyVault``.

Format du secret : ``mk_<prefix>_<random>`` où ``prefix`` (8 caractères base32) sert à
retrouver la clé côté serveur sans exposer le secret. Seule l'empreinte SHA-256 salée
(poivre = secret applicatif) est persistée.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

from flash.application.merchants.api_keys import GeneratedApiKey

_ALPHABET = "abcdefghijklmnopqrstuvwxyz0123456789"
_PREFIX_LEN = 8
_SECRET_LEN = 32


class Sha256MerchantApiKeyVault:
    def __init__(self, pepper: str) -> None:
        self._pepper = pepper.encode()

    def _rand(self, n: int) -> str:
        return "".join(secrets.choice(_ALPHABET) for _ in range(n))

    def generate(self) -> GeneratedApiKey:
        prefix = self._rand(_PREFIX_LEN)
        secret = f"mk_{prefix}_{self._rand(_SECRET_LEN)}"
        return GeneratedApiKey(secret=secret, prefix=prefix, secret_hash=self.hash(secret))

    def hash(self, secret: str) -> str:
        return hashlib.sha256(self._pepper + secret.encode()).hexdigest()

    def matches(self, secret: str, secret_hash: str) -> bool:
        return hmac.compare_digest(self.hash(secret), secret_hash)

    def prefix_of(self, secret: str) -> str:
        parts = secret.split("_")
        if len(parts) != 3 or parts[0] != "mk" or not parts[1]:
            return ""
        return parts[1]


__all__ = ["Sha256MerchantApiKeyVault"]
