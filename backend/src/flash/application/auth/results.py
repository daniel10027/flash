"""Résultat partagé des cas d'usage d'authentification (jetons de session)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from flash.application.auth.tokens import TokenPair


@dataclass(frozen=True, slots=True)
class SessionTokens:
    access_token: str
    refresh_token: str
    access_expires_in: int
    refresh_expires_in: int
    user_id: str | None = None

    @classmethod
    def from_pair(cls, pair: TokenPair, *, user_id: str | None = None) -> SessionTokens:
        return cls(
            access_token=pair.access_token,
            refresh_token=pair.refresh_token,
            access_expires_in=pair.access_expires_in,
            refresh_expires_in=pair.refresh_expires_in,
            user_id=user_id,
        )

    def to_dict(self) -> dict[str, Any]:
        body: dict[str, Any] = {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "access_expires_in": self.access_expires_in,
            "refresh_expires_in": self.refresh_expires_in,
        }
        if self.user_id is not None:
            body["user_id"] = self.user_id
        return body


__all__ = ["SessionTokens"]
