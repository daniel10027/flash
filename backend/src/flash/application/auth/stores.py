"""Ports de stockage pour l'authentification.

- ``RefreshTokenStore`` : suit le ``jti`` du *refresh token* courant par (utilisateur,
  appareil). La rotation invalide l'ancien ``jti`` ; un refresh rejoué est refusé
  (détection de vol de jeton).
- ``AccessRevocationStore`` : liste de révocation des ``jti`` d'*access token*
  (déconnexion immédiate), avec TTL = durée de vie restante du jeton.
- ``RateLimiter`` : compteur à fenêtre fixe ; ``hit`` renvoie ``False`` quand le quota
  est dépassé.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class RefreshTokenStore(Protocol):
    def remember(self, *, user_id: str, device_id: str, jti: str, ttl_seconds: int) -> None: ...

    def is_current(self, *, user_id: str, device_id: str, jti: str) -> bool: ...

    def forget(self, *, user_id: str, device_id: str) -> None: ...


@runtime_checkable
class AccessRevocationStore(Protocol):
    def revoke(self, jti: str, *, ttl_seconds: int) -> None: ...

    def is_revoked(self, jti: str) -> bool: ...


@runtime_checkable
class RateLimiter(Protocol):
    def hit(self, key: str, *, limit: int, per_seconds: int) -> bool: ...


__all__ = ["AccessRevocationStore", "RateLimiter", "RefreshTokenStore"]
