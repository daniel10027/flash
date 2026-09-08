"""Base de la couche application : ``Command`` et ``UseCase``.

Un cas d'usage = une classe avec une seule méthode publique ``execute(command) -> result``.
Il orchestre : ouverture d'une Unit of Work, idempotence, chargement d'agrégats via les
ports, application des règles de domaine, persistance, publication d'événements. Il ne
contient **aucune règle métier dure** (celles-ci vivent dans ``domain``).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Command:
    """Marqueur des commandes applicatives (données d'entrée immuables d'un cas d'usage)."""


class UseCase[C: Command, R](ABC):
    """Contrat d'un cas d'usage."""

    @abstractmethod
    def execute(self, command: C) -> R:
        raise NotImplementedError


__all__ = ["Command", "UseCase"]
