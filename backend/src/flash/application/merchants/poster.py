"""Affiche marchande imprimable (BE-069) : une image PNG A5 portant le QR statique du
marchand, son nom et une consigne. Le rendu concret est un adaptateur d'infrastructure
(``MerchantPosterRenderer``) — le domaine n'importe aucune bibliothèque graphique.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from flash.application.merchants.operations import NotAMerchant
from flash.application.services import AppServices
from flash.application.use_case import Command, UseCase
from flash.domain.shared.identifiers import EntityId


@dataclass(frozen=True, slots=True)
class Poster:
    content: bytes
    media_type: str
    filename: str


@runtime_checkable
class MerchantPosterRenderer(Protocol):
    def render(self, *, merchant_name: str, qr_payload: str, category: str) -> bytes: ...


@dataclass(frozen=True, slots=True)
class RenderMerchantPosterCommand(Command):
    merchant_user_id: str


class RenderMerchantPoster(UseCase[RenderMerchantPosterCommand, Poster]):
    def __init__(self, *, services: AppServices, renderer: MerchantPosterRenderer) -> None:
        self._services = services
        self._renderer = renderer

    def execute(self, command: RenderMerchantPosterCommand) -> Poster:
        with self._services.uow() as uow:
            merchant = uow.merchants.get_by_user_id(EntityId(command.merchant_user_id))
            if merchant is None:
                raise NotAMerchant()
            png = self._renderer.render(
                merchant_name=merchant.display_name,
                qr_payload=merchant.static_qr_payload(),
                category=merchant.category,
            )
            slug = merchant.display_name.lower().replace(" ", "-")
            return Poster(content=png, media_type="image/png", filename=f"flash-{slug}.png")


__all__ = [
    "MerchantPosterRenderer",
    "Poster",
    "RenderMerchantPoster",
    "RenderMerchantPosterCommand",
]
