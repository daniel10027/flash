"""Service OTP : génération, stockage Redis, vérification, et canaux d'envoi.

Le code n'est jamais stocké en clair : Redis ne contient qu'un SHA-256 salé (poivre =
secret applicatif) et un compteur de tentatives, le tout avec TTL. Un code correct est
consommé immédiatement.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from typing import Protocol, runtime_checkable

import structlog
from redis import Redis

from flash.application.ports import OtpPurpose
from flash.domain.shared.errors import OtpInvalid, OtpTooManyAttempts
from flash.domain.shared.identifiers import Msisdn

_log = structlog.get_logger("flash.otp")
_CODE_ALPHABET = "0123456789"


def _generate_code(length: int = 6) -> str:
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(length))


@runtime_checkable
class OtpChannel(Protocol):
    """Transport d'un code vers un numéro (SMS en production)."""

    def send(self, msisdn: Msisdn, code: str, purpose: OtpPurpose) -> None: ...


class ConsoleOtpChannel:
    """Canal de développement : journalise le code au lieu de l'envoyer par SMS."""

    def send(self, msisdn: Msisdn, code: str, purpose: OtpPurpose) -> None:
        _log.info("otp_code_dev", msisdn=msisdn.masked(), purpose=purpose.value, code=code)


class RedisOtpService:
    def __init__(
        self,
        redis: Redis[bytes],
        channel: OtpChannel,
        *,
        pepper: str,
        ttl_seconds: int = 300,
        max_attempts: int = 5,
        code_length: int = 6,
    ) -> None:
        self._redis = redis
        self._channel = channel
        self._pepper = pepper.encode()
        self._ttl = ttl_seconds
        self._max_attempts = max_attempts
        self._code_length = code_length

    def issue(self, msisdn: Msisdn, purpose: OtpPurpose) -> None:
        code = _generate_code(self._code_length)
        key = self._key(msisdn, purpose)
        pipe = self._redis.pipeline()
        pipe.delete(key)
        pipe.hset(key, mapping={"hash": self._digest(code), "attempts": "0"})
        pipe.expire(key, self._ttl)
        pipe.execute()
        self._channel.send(msisdn, code, purpose)

    def verify(self, msisdn: Msisdn, purpose: OtpPurpose, code: str) -> None:
        key = self._key(msisdn, purpose)
        stored = self._redis.hgetall(key)
        if not stored:
            raise OtpInvalid()

        attempts = int(stored[b"attempts"]) + 1
        if attempts > self._max_attempts:
            self._redis.delete(key)
            raise OtpTooManyAttempts()

        if not hmac.compare_digest(stored[b"hash"].decode(), self._digest(code)):
            self._redis.hset(key, "attempts", str(attempts))
            raise OtpInvalid()

        self._redis.delete(key)  # code consommé

    def _key(self, msisdn: Msisdn, purpose: OtpPurpose) -> str:
        return f"otp:{purpose.value}:{msisdn.value}"

    def _digest(self, code: str) -> str:
        return hashlib.sha256(self._pepper + code.encode()).hexdigest()


__all__ = ["ConsoleOtpChannel", "OtpChannel", "RedisOtpService"]
