"""Émission et vérification des JSON Web Tokens.

- *access token* : court (15 min par défaut), porte ``sub`` (utilisateur) et ``did``
  (appareil). Vérifié à chaque requête ; révocable via ``AccessRevocationStore``.
- *refresh token* : long (30 j), lié à l'appareil. À chaque rafraîchissement il est
  **remplacé** (rotation) : l'ancien ``jti`` cesse d'être « courant » et tout rejeu est
  rejeté (``TokenReused``).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from flash.domain.shared.identifiers import EntityId
from flash.interface.security.principal import AuthPrincipal
from flash.interface.security.stores import AccessRevocationStore, RefreshTokenStore

_ALGORITHM = "HS256"
_ACCESS = "access"
_REFRESH = "refresh"


class TokenError(Exception):
    """Jeton absent, malformé, expiré, de mauvais type, révoqué ou rejoué."""


class TokenReused(TokenError):
    """Un refresh token qui n'est plus le jeton courant a été présenté."""


@dataclass(frozen=True, slots=True)
class TokenPair:
    access_token: str
    refresh_token: str
    access_expires_in: int
    refresh_expires_in: int


class TokenService:
    def __init__(
        self,
        *,
        secret: str,
        access_ttl_seconds: int,
        refresh_ttl_seconds: int,
        refresh_store: RefreshTokenStore,
        revocation_store: AccessRevocationStore,
        clock: Any | None = None,
    ) -> None:
        self._secret = secret
        self._access_ttl = access_ttl_seconds
        self._refresh_ttl = refresh_ttl_seconds
        self._refresh_store = refresh_store
        self._revocation = revocation_store
        self._now = clock.now if clock is not None else lambda: datetime.now(UTC)

    # ------------------------------------------------------------------ émission
    def issue_pair(self, *, user_id: EntityId, device_id: str) -> TokenPair:
        access, _ = self._encode(_ACCESS, str(user_id), device_id, self._access_ttl)
        refresh, refresh_jti = self._encode(_REFRESH, str(user_id), device_id, self._refresh_ttl)
        self._refresh_store.remember(
            user_id=str(user_id),
            device_id=device_id,
            jti=refresh_jti,
            ttl_seconds=self._refresh_ttl,
        )
        return TokenPair(
            access_token=access,
            refresh_token=refresh,
            access_expires_in=self._access_ttl,
            refresh_expires_in=self._refresh_ttl,
        )

    def rotate(self, refresh_token: str) -> TokenPair:
        claims = self._decode(refresh_token, expected_type=_REFRESH)
        user_id, device_id, jti = claims["sub"], claims["did"], claims["jti"]
        if not self._refresh_store.is_current(user_id=user_id, device_id=device_id, jti=jti):
            # Rejeu d'un ancien refresh -> on coupe la session de l'appareil.
            self._refresh_store.forget(user_id=user_id, device_id=device_id)
            raise TokenReused("Refresh token déjà utilisé ou révoqué.")
        return self.issue_pair(user_id=EntityId(user_id), device_id=device_id)

    # ---------------------------------------------------------------- vérification
    def verify_access(self, access_token: str) -> AuthPrincipal:
        claims = self._decode(access_token, expected_type=_ACCESS)
        if self._revocation.is_revoked(claims["jti"]):
            raise TokenError("Jeton révoqué.")
        return AuthPrincipal(
            user_id=EntityId(claims["sub"]),
            device_id=claims["did"],
            token_id=claims["jti"],
        )

    def revoke_access(
        self, principal: AuthPrincipal, *, remaining_seconds: int | None = None
    ) -> None:
        self._revocation.revoke(
            principal.token_id, ttl_seconds=remaining_seconds or self._access_ttl
        )

    def logout(self, principal: AuthPrincipal) -> None:
        self.revoke_access(principal)
        self._refresh_store.forget(user_id=str(principal.user_id), device_id=principal.device_id)

    # -------------------------------------------------------------------- interne
    def _encode(self, token_type: str, sub: str, device_id: str, ttl: int) -> tuple[str, str]:
        issued = self._now()
        jti = uuid.uuid4().hex
        payload = {
            "sub": sub,
            "did": device_id,
            "type": token_type,
            "jti": jti,
            "iat": int(issued.timestamp()),
            "exp": int((issued + timedelta(seconds=ttl)).timestamp()),
        }
        return jwt.encode(payload, self._secret, algorithm=_ALGORITHM), jti

    def _decode(self, token: str, *, expected_type: str) -> dict[str, Any]:
        try:
            claims: dict[str, Any] = jwt.decode(token, self._secret, algorithms=[_ALGORITHM])
        except jwt.ExpiredSignatureError as exc:
            raise TokenError("Jeton expiré.") from exc
        except jwt.InvalidTokenError as exc:
            raise TokenError("Jeton invalide.") from exc
        if claims.get("type") != expected_type:
            raise TokenError(f"Type de jeton inattendu (attendu : {expected_type}).")
        return claims


__all__ = ["TokenError", "TokenPair", "TokenReused", "TokenService"]
