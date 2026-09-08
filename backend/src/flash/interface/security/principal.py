"""Identité authentifiée attachée à une requête."""

from __future__ import annotations

from dataclasses import dataclass

from flash.domain.shared.identifiers import EntityId


@dataclass(frozen=True, slots=True)
class AuthPrincipal:
    """Sujet authentifié : l'utilisateur, l'appareil, et le ``jti`` du jeton présenté."""

    user_id: EntityId
    device_id: str
    token_id: str


__all__ = ["AuthPrincipal"]
