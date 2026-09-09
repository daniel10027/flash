"""Jeu de données de démonstration (BE-046) — ``flash seed``.

Idempotent : relancé, il ne recrée pas les comptes déjà présents.
Pays (CI/SN), grille tarifaire (0,8 %) et plafonds KYC viennent déjà des référentiels
statiques ; ce script se contente de créer des acteurs et de les approvisionner via un
dépôt agent (donc ledger équilibré).
"""

from __future__ import annotations

from flash.application.cash.operations import (
    CreateCashDeposit,
    CreateCashDepositCommand,
    EnrollAgent,
    EnrollAgentCommand,
)
from flash.application.merchants.operations import EnrollMerchant, EnrollMerchantCommand
from flash.domain.identity.pin import Pin
from flash.domain.identity.user import User
from flash.domain.limits.limits import KycPolicy, LimitPolicy
from flash.domain.shared.identifiers import CountryCode, EntityId, Msisdn
from flash.domain.shared.money import Currency
from flash.domain.wallet.wallet import Wallet
from flash.infrastructure.config import Settings
from flash.infrastructure.limits import NullLimitCounter, build_limit_repository
from flash.infrastructure.security.pin_hasher import Argon2PinHasher
from flash.interface.container import build_app_services

_PIN = "1397"
_CI = CountryCode("CI")
_XOF = Currency.of("XOF")

# (msisdn, dépôt initial en unité mineure) — sous le plafond par opération du palier 0
# (200 000 XOF).
_USERS = [
    ("+2250700000101", 150_000),
    ("+2250700000102", 90_000),
]
_AGENT_MSISDN = "+2250700000199"
_MERCHANT_MSISDN = "+2250700000188"


def seed_demo(settings: Settings) -> list[str]:
    services = build_app_services(settings)
    hasher = Argon2PinHasher()
    out: list[str] = []

    def ensure_user(msisdn: str) -> str:
        with services.uow() as uow:
            existing = uow.users.get_by_msisdn(Msisdn(msisdn))
            if existing is not None:
                return str(existing.id)
            user = User.register(
                user_id=EntityId(str(services.ids.new_id())),
                country=_CI,
                msisdn=Msisdn(msisdn),
                pin_hash=hasher.hash(Pin(_PIN)),
                now=services.clock.now(),
            )
            user.activate(services.clock.now())
            user.pull_events()
            wallet = Wallet.open(
                wallet_id=EntityId(str(services.ids.new_id())),
                user_id=user.id,
                currency=_XOF,
                now=services.clock.now(),
            )
            wallet.pull_events()
            uow.users.add(user)
            uow.wallets.add(wallet)
            uow.commit()
            out.append(f"compte créé : {Msisdn(msisdn).masked()} (PIN {_PIN})")
            return str(user.id)

    agent_user_id = ensure_user(_AGENT_MSISDN)
    merchant_user_id = ensure_user(_MERCHANT_MSISDN)
    user_ids = [ensure_user(msisdn) for msisdn, _ in _USERS]

    with services.uow() as uow:
        already_agent = uow.agents.get_by_user_id(EntityId(agent_user_id)) is not None
    if not already_agent:
        view = EnrollAgent(services=services).execute(
            EnrollAgentCommand(
                user_id=agent_user_id,
                float_cap_minor=50_000_000,
                initial_float_minor=10_000_000,
                commission_bps=100,
            )
        )
        out.append(f"agent enrôlé : {view.agent_id} (float {view.float_available_minor})")

    with services.uow() as uow:
        already_merchant = uow.merchants.get_by_user_id(EntityId(merchant_user_id)) is not None
    if not already_merchant:
        m = EnrollMerchant(services=services).execute(
            EnrollMerchantCommand(
                user_id=merchant_user_id, display_name="Café de la Gare", fee_bps=100
            )
        )
        out.append(f"marchand enrôlé : {m.merchant_id} — QR {m.static_qr_payload}")

    deposit = CreateCashDeposit(
        services=services,
        limits=LimitPolicy(build_limit_repository(), NullLimitCounter()),
        kyc=KycPolicy(),
    )
    for (msisdn, amount), uid in zip(_USERS, user_ids, strict=True):
        with services.uow() as uow:
            wallet = uow.wallets.list_for_user(EntityId(uid))[0]
            funded = wallet.available.amount_minor >= amount
        if funded:
            continue
        deposit.execute(
            CreateCashDepositCommand(
                agent_user_id=agent_user_id,
                client_phone_number=msisdn,
                amount_minor=amount,
                idempotency_key=f"seed-deposit-{Msisdn(msisdn).value}",
                country="CI",
            )
        )
        out.append(f"approvisionné : {Msisdn(msisdn).masked()} +{amount} XOF")

    if not out:
        out.append("rien à faire : le jeu de démo est déjà en place")
    return out


__all__ = ["seed_demo"]
