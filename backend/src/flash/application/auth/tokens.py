"""Émission, rotation et vérification des jetons de session.

Politique (application) :
- *access token* court, porte ``sub`` (utilisateur) + ``did`` (appareil) ; vérifié à
  chaque requête, révocable via ``AccessRevocationStore`` ;
- *refresh token* long, lié à l'appareil ; **remplacé à chaque rafraîchissement**
  (rotation). Rejouer un ancien refresh est refusé (``TokenReused``) et coupe la session
  de l'appareil.

L'encodage/décodage concret (JWT) est délégué au port ``TokenCodec`` : ce module ne
connaît aucune bibliothèque de jeton.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from flash.application.auth.principal import AuthPrincipal
from flash.application.auth.stores import AccessRevocationStore, RefreshTokenStore
from flash.domain.shared.identifiers import EntityId

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


@runtime_checkable
class TokenCodec(Protocol):
    """Sérialise/désérialise un jeu de revendications signé et daté.

    ``encode`` produit un jeton opaque avec expiration ``ttl_seconds``. ``decode`` renvoie
    les revendications ou lève ``TokenError`` (signature invalide, expiration, format).
    """

    def encode(self, claims: dict[str, Any], *, ttl_seconds: int) -> str: ...

    def decode(self, token: str) -> dict[str, Any]: ...


class TokenService:
    def __init__(
        self,
        *,
        codec: TokenCodec,
        access_ttl_seconds: int,
        refresh_ttl_seconds: int,
        refresh_store: RefreshTokenStore,
        revocation_store: AccessRevocationStore,
    ) -> None:
        self._codec = codec
        self._access_ttl = access_ttl_seconds
        self._refresh_ttl = refresh_ttl_seconds
        self._refresh_store = refresh_store
        self._revocation = revocation_store

    # ------------------------------------------------------------------ émission
    def issue_pair(self, *, user_id: EntityId, device_id: str) -> TokenPair:
        access, _ = self._issue(_ACCESS, str(user_id), device_id, self._access_ttl)
        refresh, refresh_jti = self._issue(_REFRESH, str(user_id), device_id, self._refresh_ttl)
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
        claims = self._read(refresh_token, expected_type=_REFRESH)
        user_id, device_id, jti = claims["sub"], claims["did"], claims["jti"]
        if not self._refresh_store.is_current(user_id=user_id, device_id=device_id, jti=jti):
            self._refresh_store.forget(user_id=user_id, device_id=device_id)
            raise TokenReused("Refresh token déjà utilisé ou révoqué.")
        return self.issue_pair(user_id=EntityId(user_id), device_id=device_id)

    # ---------------------------------------------------------------- vérification
    def verify_access(self, access_token: str) -> AuthPrincipal:
        claims = self._read(access_token, expected_type=_ACCESS)
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
    def _issue(self, token_type: str, sub: str, device_id: str, ttl: int) -> tuple[str, str]:
        jti = uuid.uuid4().hex
        claims = {"sub": sub, "did": device_id, "type": token_type, "jti": jti}
        return self._codec.encode(claims, ttl_seconds=ttl), jti

    def _read(self, token: str, *, expected_type: str) -> dict[str, Any]:
        claims = self._codec.decode(token)
        if claims.get("type") != expected_type:
            raise TokenError(f"Type de jeton inattendu (attendu : {expected_type}).")
        return claims


__all__ = ["TokenCodec", "TokenError", "TokenPair", "TokenReused", "TokenService"]
