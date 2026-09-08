"""Conversions ORM ↔ domaine.

Un sens (``*_to_domain``) reconstruit un agrégat pur à partir des lignes. L'autre
(``*_to_model``) produit un modèle ORM prêt à être ``merge`` dans une session. Aucune
règle métier ici : uniquement du recopiage de champs.
"""

from __future__ import annotations

from uuid import NAMESPACE_URL, uuid5

from flash.domain.agent.agent import Agent, AgentStatus
from flash.domain.cash.order import CashOrder, CashOrderStatus, CashOrderType
from flash.domain.identity.kyc import KycTier
from flash.domain.identity.kyc_case import (
    KycCase,
    KycCaseStatus,
    KycDocument,
    KycDocumentKind,
)
from flash.domain.identity.user import PhoneNumber, User, UserStatus
from flash.domain.ledger.chart import Direction
from flash.domain.ledger.transaction import LedgerTransaction, Posting, TransactionKind
from flash.domain.payments.request import PaymentRequest, PaymentRequestStatus
from flash.domain.shared.identifiers import CountryCode, EntityId, Msisdn
from flash.domain.shared.money import Currency, Money
from flash.domain.wallet.wallet import Wallet, WalletStatus
from flash.infrastructure.db.models import (
    AgentModel,
    CashOrderModel,
    KycCaseModel,
    KycDocumentModel,
    LedgerPostingModel,
    LedgerTransactionModel,
    PaymentRequestModel,
    PhoneNumberModel,
    UserModel,
    WalletModel,
)

# --------------------------------------------------------------------- identité


def _phone_number_id(user_id: str, msisdn: str) -> str:
    """Identifiant déterministe d'un numéro : stable d'une écriture à l'autre (upsert)."""
    return str(uuid5(NAMESPACE_URL, f"flash:phone:{user_id}:{msisdn}"))


def user_to_domain(model: UserModel) -> User:
    phones = [
        PhoneNumber(
            msisdn=Msisdn(p.msisdn),
            linked_at=p.linked_at,
            is_primary=p.is_primary,
            verified_at=p.verified_at,
        )
        for p in sorted(model.phone_numbers, key=lambda p: p.linked_at)
    ]
    return User(
        id=EntityId(model.id),
        country=CountryCode(model.country),
        status=UserStatus(model.status),
        kyc_tier=KycTier(model.kyc_tier),
        phone_numbers=phones,
        created_at=model.created_at,
        pin_hash=model.pin_hash,
    )


def user_to_model(user: User) -> UserModel:
    return UserModel(
        id=str(user.id),
        country=user.country.value,
        status=user.status.value,
        kyc_tier=int(user.kyc_tier),
        pin_hash=user.pin_hash,
        created_at=user.created_at,
        phone_numbers=[
            PhoneNumberModel(
                id=_phone_number_id(str(user.id), p.msisdn.value),
                user_id=str(user.id),
                msisdn=p.msisdn.value,
                is_primary=p.is_primary,
                linked_at=p.linked_at,
                verified_at=p.verified_at,
            )
            for p in user.phone_numbers
        ],
    )


# ----------------------------------------------------------------------- wallet


def wallet_to_domain(model: WalletModel) -> Wallet:
    currency = Currency.of(model.currency)
    return Wallet(
        id=EntityId(model.id),
        user_id=EntityId(model.user_id),
        currency=currency,
        available=Money(model.available_minor, currency),
        reserved=Money(model.reserved_minor, currency),
        created_at=model.created_at,
        status=WalletStatus(model.status),
    )


def wallet_to_model(wallet: Wallet) -> WalletModel:
    return WalletModel(
        id=str(wallet.id),
        user_id=str(wallet.user_id),
        currency=wallet.currency.code,
        status=wallet.status.value,
        available_minor=wallet.available.amount_minor,
        reserved_minor=wallet.reserved.amount_minor,
        created_at=wallet.created_at,
    )


# ----------------------------------------------------------------------- ledger


def ledger_transaction_to_model(txn: LedgerTransaction) -> LedgerTransactionModel:
    return LedgerTransactionModel(
        id=str(txn.id),
        kind=txn.kind.value,
        occurred_at=txn.occurred_at,
        reference=txn.reference,
        reason=txn.reason,
        tx_metadata=dict(txn.metadata),
        reverses_transaction_id=(
            str(txn.reverses_transaction_id) if txn.reverses_transaction_id else None
        ),
        postings=[
            LedgerPostingModel(
                account_id=str(p.account_id),
                direction=p.direction.value,
                amount_minor=p.amount.amount_minor,
                currency=p.amount.currency.code,
                wallet_id=str(p.wallet_id) if p.wallet_id else None,
                analytic=p.analytic,
            )
            for p in txn.postings
        ],
    )


def ledger_transaction_to_domain(model: LedgerTransactionModel) -> LedgerTransaction:
    postings = tuple(
        Posting(
            account_id=EntityId(p.account_id),
            direction=Direction(p.direction),
            amount=Money(p.amount_minor, Currency.of(p.currency)),
            wallet_id=EntityId(p.wallet_id) if p.wallet_id else None,
            analytic=p.analytic,
        )
        for p in model.postings
    )
    return LedgerTransaction(
        id=EntityId(model.id),
        kind=TransactionKind(model.kind),
        postings=postings,
        occurred_at=model.occurred_at,
        reference=model.reference,
        reason=model.reason,
        metadata=dict(model.tx_metadata),
        reverses_transaction_id=(
            EntityId(model.reverses_transaction_id) if model.reverses_transaction_id else None
        ),
    )


# ------------------------------------------------------------------------ agent


def agent_to_domain(model: AgentModel) -> Agent:
    currency = Currency.of(model.currency)
    return Agent(
        id=EntityId(model.id),
        user_id=EntityId(model.user_id),
        currency=currency,
        float_available=Money(model.float_available_minor, currency),
        float_cap=Money(model.float_cap_minor, currency),
        commission_bps=model.commission_bps,
        created_at=model.created_at,
        status=AgentStatus(model.status),
    )


def agent_to_model(agent: Agent) -> AgentModel:
    return AgentModel(
        id=str(agent.id),
        user_id=str(agent.user_id),
        currency=agent.currency.code,
        float_available_minor=agent.float_available.amount_minor,
        float_cap_minor=agent.float_cap.amount_minor,
        commission_bps=agent.commission_bps,
        status=agent.status.value,
        created_at=agent.created_at,
    )


# ------------------------------------------------------------------- ordre cash


def cash_order_to_domain(model: CashOrderModel) -> CashOrder:
    currency = Currency.of(model.currency)
    return CashOrder(
        id=EntityId(model.id),
        type=CashOrderType(model.type),
        client_id=EntityId(model.client_id),
        amount=Money(model.amount_minor, currency),
        fee=Money(model.fee_minor, currency),
        currency_code=model.currency,
        status=CashOrderStatus(model.status),
        created_at=model.created_at,
        agent_id=EntityId(model.agent_id) if model.agent_id else None,
        code_hash=model.code_hash,
        expires_at=model.expires_at,
        ledger_transaction_id=(
            EntityId(model.ledger_transaction_id) if model.ledger_transaction_id else None
        ),
    )


def cash_order_to_model(order: CashOrder) -> CashOrderModel:
    return CashOrderModel(
        id=str(order.id),
        type=order.type.value,
        client_id=str(order.client_id),
        agent_id=str(order.agent_id) if order.agent_id else None,
        amount_minor=order.amount.amount_minor,
        fee_minor=order.fee.amount_minor,
        currency=order.currency_code,
        status=order.status.value,
        code_hash=order.code_hash,
        expires_at=order.expires_at,
        ledger_transaction_id=(
            str(order.ledger_transaction_id) if order.ledger_transaction_id else None
        ),
        created_at=order.created_at,
    )


def _kyc_document_id(case_id: str, kind: str) -> str:
    """Identifiant déterministe d'une pièce : stable d'un ``merge`` à l'autre."""
    return str(uuid5(NAMESPACE_URL, f"flash:kyc-doc:{case_id}:{kind}"))


def kyc_case_to_domain(model: KycCaseModel) -> KycCase:
    return KycCase(
        id=EntityId(model.id),
        user_id=EntityId(model.user_id),
        target_tier=KycTier(model.target_tier),
        status=KycCaseStatus(model.status),
        documents=[
            KycDocument(
                kind=KycDocumentKind(d.kind),
                storage_key=d.storage_key,
                content_type=d.content_type,
                byte_size=d.byte_size,
                uploaded_at=d.uploaded_at,
            )
            for d in model.documents
        ],
        submitted_at=model.submitted_at,
        decided_at=model.decided_at,
        reviewer_id=EntityId(model.reviewer_id) if model.reviewer_id else None,
        decision_reason=model.decision_reason,
    )


def kyc_case_to_model(case: KycCase) -> KycCaseModel:
    return KycCaseModel(
        id=str(case.id),
        user_id=str(case.user_id),
        target_tier=int(case.target_tier),
        status=case.status.value,
        submitted_at=case.submitted_at,
        decided_at=case.decided_at,
        reviewer_id=str(case.reviewer_id) if case.reviewer_id else None,
        decision_reason=case.decision_reason,
        documents=[
            KycDocumentModel(
                id=_kyc_document_id(str(case.id), d.kind.value),
                case_id=str(case.id),
                kind=d.kind.value,
                storage_key=d.storage_key,
                content_type=d.content_type,
                byte_size=d.byte_size,
                uploaded_at=d.uploaded_at,
            )
            for d in case.documents
        ],
    )


def payment_request_to_domain(model: PaymentRequestModel) -> PaymentRequest:
    currency = Currency.of(model.currency)
    return PaymentRequest(
        id=EntityId(model.id),
        requester_id=EntityId(model.requester_id),
        payer_id=EntityId(model.payer_id),
        amount=Money(model.amount_minor, currency),
        currency_code=model.currency,
        status=PaymentRequestStatus(model.status),
        created_at=model.created_at,
        expires_at=model.expires_at,
        note=model.note,
        resulting_transfer_id=(
            EntityId(model.resulting_transfer_id) if model.resulting_transfer_id else None
        ),
    )


def payment_request_to_model(request: PaymentRequest) -> PaymentRequestModel:
    return PaymentRequestModel(
        id=str(request.id),
        requester_id=str(request.requester_id),
        payer_id=str(request.payer_id),
        amount_minor=request.amount.amount_minor,
        currency=request.currency_code,
        status=request.status.value,
        note=request.note,
        created_at=request.created_at,
        expires_at=request.expires_at,
        resulting_transfer_id=(
            str(request.resulting_transfer_id) if request.resulting_transfer_id else None
        ),
    )


__all__ = [
    "agent_to_domain",
    "agent_to_model",
    "cash_order_to_domain",
    "cash_order_to_model",
    "kyc_case_to_domain",
    "kyc_case_to_model",
    "ledger_transaction_to_domain",
    "ledger_transaction_to_model",
    "payment_request_to_domain",
    "payment_request_to_model",
    "user_to_domain",
    "user_to_model",
    "wallet_to_domain",
    "wallet_to_model",
]
