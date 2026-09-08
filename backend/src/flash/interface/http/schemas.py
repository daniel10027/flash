"""Base des schémas de requête/réponse (pydantic v2)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ApiModel(BaseModel):
    """Modèle strict : rejette les champs inconnus, immuable après validation."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


__all__ = ["ApiModel"]
