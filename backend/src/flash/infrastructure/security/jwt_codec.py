"""``JwtTokenCodec`` — implémentation JWT (HS256) du port ``TokenCodec``."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from flash.application.auth.tokens import TokenError
from flash.domain.shared.ports import Clock

_ALGORITHM = "HS256"


class JwtTokenCodec:
    def __init__(self, secret: str, *, clock: Clock | None = None) -> None:
        self._secret = secret
        self._now = clock.now if clock is not None else lambda: datetime.now(UTC)

    def encode(self, claims: dict[str, Any], *, ttl_seconds: int) -> str:
        issued = self._now()
        payload = {
            **claims,
            "iat": int(issued.timestamp()),
            "exp": int((issued + timedelta(seconds=ttl_seconds)).timestamp()),
        }
        return jwt.encode(payload, self._secret, algorithm=_ALGORITHM)

    def decode(self, token: str) -> dict[str, Any]:
        try:
            decoded: dict[str, Any] = jwt.decode(token, self._secret, algorithms=[_ALGORITHM])
        except jwt.ExpiredSignatureError as exc:
            raise TokenError("Jeton expiré.") from exc
        except jwt.InvalidTokenError as exc:
            raise TokenError("Jeton invalide.") from exc
        return decoded


__all__ = ["JwtTokenCodec"]
