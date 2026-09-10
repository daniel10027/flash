"""Jeu de données de démonstration (BE-046, enrichi) — ``flash seed``.

Idempotent : relancé, il ne recrée rien qui existe déjà.

Crée un acteur de chaque **profil** et les approvisionne (via un dépôt agent —
ledger équilibré) :

* 4 clients : deux au palier KYC 0, un au **palier 1** (dossier soumis + approuvé),
  un avec un **dossier KYC en attente** (pour la file du back-office) ;
* 1 **agent** avec float et commission ;
* 1 **marchand** : enrôlé, **KYB approuvé**, une **clé d'API** ``/merchant/v1``,
  une **caisse** (sous-compte).

Les identifiants exacts sont rappelés dans ``docs/GUIDE.md``.
"""

from __future__ import annotations

from dataclasses import dataclass

from flash.application.cash.operations import (
    CreateCashDeposit,
    CreateCashDepositCommand,
    EnrollAgent,
    EnrollAgentCommand,
)
from flash.application.identity.kyc import (
    KycDocumentInput,
    ReviewKyc,
    ReviewKycCommand,
    SubmitKyc,
    SubmitKycCommand,
)
from flash.application.merchants.api_keys import (
    IssueMerchantApiKey,
    IssueMerchantApiKeyCommand,
)
from flash.application.merchants.kyb import (
    ReviewMerchantKyb,
    ReviewMerchantKybCommand,
    SubmitMerchantKyb,
    SubmitMerchantKybCommand,
)
from flash.application.merchants.operations import EnrollMerchant, EnrollMerchantCommand
from flash.application.merchants.sub_accounts import (
    CreateSubAccount,
    CreateSubAccountCommand,
)
from flash.domain.identity.pin import Pin
from flash.domain.identity.user import User
from flash.domain.limits.limits import KycPolicy, LimitPolicy
from flash.domain.shared.identifiers import CountryCode, EntityId, Msisdn
from flash.domain.shared.money import Currency
from flash.domain.wallet.wallet import Wallet
from flash.infrastructure.config import Settings
from flash.infrastructure.limits import NullLimitCounter, build_limit_repository
from flash.infrastructure.security.pin_hasher import Argon2PinHasher
from flash.interface.container import build_deps
from flash.interface.security.wiring import build_security

_PIN = "1397"
_CI = CountryCode("CI")
_XOF = Currency.of("XOF")
_REVIEWER = "00000000-0000-0000-0000-0000000000aa"

# Un PNG 1x1 valide, réutilisé comme pièce justificative factice.
_PNG_1x1 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


@dataclass(frozen=True, slots=True)
class _Person:
    msisdn: str
    label: str
    deposit_minor: int
    kyc: str  # "none" | "tier1" | "pending"


_CLIENTS = [
    _Person("+2250700000101", "Awa (cliente, KYC 0)", 150_000, "none"),
    _Person("+2250700000102", "Kofi (client, KYC 0)", 90_000, "none"),
    _Person("+2250700000103", "Fatou (cliente, KYC 1)", 500_000, "tier1"),
    _Person("+2250700000104", "Yao (client, KYC en attente)", 120_000, "pending"),
]
_AGENT = _Person("+2250700000199", "Agence Centrale (agent)", 0, "none")
_MERCHANT = _Person("+2250700000188", "Café de la Gare (marchand)", 0, "none")


def seed_demo(settings: Settings) -> list[str]:
    bundle = build_security(settings)
    deps = build_deps(settings, tokens=bundle.tokens)
    services = deps.services
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

    agent_uid = ensure_user(_AGENT.msisdn)
    merchant_uid = ensure_user(_MERCHANT.msisdn)
    client_uids = {p.msisdn: ensure_user(p.msisdn) for p in _CLIENTS}

    # ---------------------------------------------------------------- agent
    with services.uow() as uow:
        is_agent = uow.agents.get_by_user_id(EntityId(agent_uid)) is not None
    if not is_agent:
        view = EnrollAgent(services=services).execute(
            EnrollAgentCommand(
                user_id=agent_uid,
                float_cap_minor=50_000_000,
                initial_float_minor=10_000_000,
                commission_bps=100,
            )
        )
        out.append(
            f"agent enrôlé : {view.agent_id} "
            f"(float {view.float_available_minor} XOF, commission 1 %)"
        )

    # ---------------------------------------------------------------- marchand
    with services.uow() as uow:
        merchant = uow.merchants.get_by_user_id(EntityId(merchant_uid))
    if merchant is None:
        m = EnrollMerchant(services=services).execute(
            EnrollMerchantCommand(
                user_id=merchant_uid, display_name="Café de la Gare", fee_bps=100
            )
        )
        out.append(f"marchand enrôlé : {m.merchant_id} — QR {m.static_qr_payload}")

        SubmitMerchantKyb(services=services).execute(
            SubmitMerchantKybCommand(merchant_user_id=merchant_uid)
        )
        ReviewMerchantKyb(services=services).execute(
            ReviewMerchantKybCommand(
                merchant_id=m.merchant_id, reviewer=_REVIEWER, approve=True, reason=""
            )
        )
        out.append("marchand : KYB approuvé")

        issued = IssueMerchantApiKey(
            services=services, vault=deps.merchant_api_key_vault
        ).execute(
            IssueMerchantApiKeyCommand(merchant_user_id=merchant_uid, label="Caisse web")
        )
        out.append(f"marchand : clé d'API émise -> {issued.secret}")

        CreateSubAccount(services=services).execute(
            CreateSubAccountCommand(
                merchant_user_id=merchant_uid,
                kind="TILL",
                label="Comptoir",
            )
        )
        out.append("marchand : caisse « Comptoir » créée")

    # ------------------------------------------------- clients : KYC (avant dépôts,
    # pour que les plafonds du palier 1 s'appliquent au moment d'approvisionner).
    docs = [
        KycDocumentInput(kind="ID_FRONT", content_base64=_PNG_1x1, content_type="image/png"),
        KycDocumentInput(kind="SELFIE", content_base64=_PNG_1x1, content_type="image/png"),
    ]
    for p in _CLIENTS:
        if p.kyc == "none":
            continue
        uid = client_uids[p.msisdn]
        with services.uow() as uow:
            has_case = bool(uow.kyc_cases.list_for_user(EntityId(uid)))
        if has_case:
            continue
        case = SubmitKyc(services=services, documents=deps.documents).execute(
            SubmitKycCommand(
                user_id=uid,
                target_tier=1,
                documents=docs,
                idempotency_key=f"seed-kyc-{Msisdn(p.msisdn).value}",
            )
        )
        if p.kyc == "tier1":
            ReviewKyc(services=services).execute(
                ReviewKycCommand(
                    case_id=case.case_id, reviewer_id=_REVIEWER, approve=True, reason=""
                )
            )
            out.append(f"KYC approuvé (palier 1) : {Msisdn(p.msisdn).masked()}")
        else:
            out.append(f"dossier KYC en attente : {Msisdn(p.msisdn).masked()} ({case.case_id})")

    # ---------------------------------------------------------------- clients : dépôts
    deposit = CreateCashDeposit(
        services=services,
        limits=LimitPolicy(build_limit_repository(), NullLimitCounter()),
        kyc=KycPolicy(),
    )
    for p in _CLIENTS:
        uid = client_uids[p.msisdn]
        with services.uow() as uow:
            wallet = uow.wallets.list_for_user(EntityId(uid))[0]
            funded = wallet.available.amount_minor >= p.deposit_minor
        if not funded:
            deposit.execute(
                CreateCashDepositCommand(
                    agent_user_id=agent_uid,
                    client_phone_number=p.msisdn,
                    amount_minor=p.deposit_minor,
                    idempotency_key=f"seed-deposit-{Msisdn(p.msisdn).value}",
                    country="CI",
                )
            )
            out.append(f"approvisionné : {Msisdn(p.msisdn).masked()} +{p.deposit_minor} XOF")

    if not out:
        out.append("rien à faire : le jeu de démo est déjà en place")

    out.append("")
    out.append("── Récapitulatif des accès (dev) ──")
    out.append(f"  PIN commun : {_PIN}")
    for p in _CLIENTS:
        out.append(f"  {p.msisdn}  {p.label}")
    out.append(f"  {_AGENT.msisdn}  {_AGENT.label}")
    out.append(f"  {_MERCHANT.msisdn}  {_MERCHANT.label}")
    out.append(
        f"  Back-office : X-Admin-Key = {settings.admin_api_key or '(non défini — voir .env)'}"
    )
    return out


__all__ = ["seed_demo"]

