"""Paliers de vérification d'identité (KYC)."""

from __future__ import annotations

from enum import IntEnum


class KycTier(IntEnum):
    """Niveau de connaissance client.

    - ``TIER_0`` : compte ouvert sur simple numéro vérifié. Plafonds bas.
    - ``TIER_1`` : pièce d'identité + selfie vérifiés. Plafonds standards.
    - ``TIER_2`` : justificatifs renforcés (adresse, revenus). Plafonds élevés.

    Les plafonds concrets par palier sont portés par le référentiel pays
    (``limits``), jamais en dur ici.
    """

    TIER_0 = 0
    TIER_1 = 1
    TIER_2 = 2

    @property
    def label(self) -> str:
        return {0: "Non vérifié", 1: "Vérifié", 2: "Vérifié renforcé"}[int(self)]


__all__ = ["KycTier"]
