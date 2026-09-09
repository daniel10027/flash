"""Conversions ORM ↔ domaine.

Un sens (``*_to_domain``) reconstruit un agrégat pur à partir des lignes. L'autre
(``*_to_model``) produit un modèle ORM prêt à être ``merge`` dans une session. Aucune
règle métier ici : uniquement du recopiage de champs.
"""

from __future__ import annotations

from uuid import NAMESPACE_URL, uuid5

from flash.domain.agent.agent import Agent, AgentStatus
from flash.domain.card.authorization import CardAuthorization, CardAuthorizationStatus
from flash.domain.card.card import Card, CardChannel, CardNetwork, CardStatus
from flash.domain.cash.order import CashOrder, CashOrderStatus, CashOrderType
from flash.domain.country.reference import Country, Operator
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
from flash.domain.merchants.charge import MerchantCharge, MerchantChargeStatus
from flash.domain.merchants.merchant import Merchant, MerchantStatus
from flash.domain.merchants.payment import MerchantPayment, MerchantPaymentStatus
from flash.domain.operators.transfer import (
    OperatorTransfer,
    OperatorTransferDirection,
    OperatorTransferStatus,
)
from flash.domain.payments.request import PaymentRequest, PaymentRequestStatus
from flash.domain.savings.plan import SavingsFrequency, SavingsPlan, SavingsPlanStatus
from flash.domain.shared.identifiers import CountryCode, EntityId, Msisdn
from flash.domain.shared.money import Currency, Money
from flash.domain.vault.vault import Vault, VaultPocket
from flash.domain.wallet.wallet import Wallet, WalletStatus
from flash.infrastructure.db.models import (
    AgentModel,
    CardAuthorizationModel,
    CardModel,
    CashOrderModel,
    CountryModel,
    KycCaseModel,
    KycDocumentModel,
    LedgerPostingModel,
    LedgerTransactionModel,
    MerchantChargeModel,
    MerchantModel,
    MerchantPaymentModel,
    OperatorModel,
    OperatorTransferModel,
    PaymentRequestModel,
    PhoneNumberModel,
    SavingsPlanModel,
    UserModel,
    VaultPocketModel,
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
        vaulted=Money(model.vaulted_minor, currency),
        saved=Money(model.saved_minor, currency),
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
        vaulted_minor=wallet.vaulted.amount_minor,
        saved_minor=wallet.saved.amount_minor,
        created_at=wallet.created_at,
    )


# ------------------------------------------------------------------------ coffre


def vault_to_domain(models: list[VaultPocketModel]) -> Vault | None:
    """Reconstruit l'agrégat ``Vault`` à partir de ses lignes de poches (ou ``None``)."""
    if not models:
        return None
    first = models[0]
    currency = Currency.of(first.currency)
    pockets = [
        VaultPocket(
            id=EntityId(m.id),
            name=m.name,
            balance=Money(m.balance_minor, currency),
            created_at=m.created_at,
            goal_minor=m.goal_minor,
            locked_until=m.locked_until,
        )
        for m in models
    ]
    return Vault(
        id=EntityId(first.vault_id),
        wallet_id=EntityId(first.wallet_id),
        user_id=EntityId(first.user_id),
        currency=currency,
        created_at=min(m.created_at for m in models),
        pockets=pockets,
    )


def vault_pockets_to_models(vault: Vault) -> list[VaultPocketModel]:
    return [
        VaultPocketModel(
            id=str(p.id),
            vault_id=str(vault.id),
            wallet_id=str(vault.wallet_id),
            user_id=str(vault.user_id),
            currency=vault.currency.code,
            name=p.name,
            balance_minor=p.balance.amount_minor,
            goal_minor=p.goal_minor,
            locked_until=p.locked_until,
            created_at=p.created_at,
        )
        for p in vault.pockets
    ]


# ----------------------------------------------------------------------- épargne


def savings_plan_to_domain(model: SavingsPlanModel) -> SavingsPlan:
    currency = Currency.of(model.currency)
    return SavingsPlan(
        id=EntityId(model.id),
        wallet_id=EntityId(model.wallet_id),
        user_id=EntityId(model.user_id),
        currency=currency,
        name=model.name,
        balance=Money(model.balance_minor, currency),
        annual_rate_bps=model.annual_rate_bps,
        frequency=SavingsFrequency(model.frequency),
        contribution=Money(model.contribution_minor, currency),
        created_at=model.created_at,
        target_minor=model.target_minor,
        target_date=model.target_date,
        next_contribution_at=model.next_contribution_at,
        last_accrual_at=model.last_accrual_at,
        accrued_micro=model.accrued_micro,
        status=SavingsPlanStatus(model.status),
    )


def savings_plan_to_model(plan: SavingsPlan) -> SavingsPlanModel:
    return SavingsPlanModel(
        id=str(plan.id),
        wallet_id=str(plan.wallet_id),
        user_id=str(plan.user_id),
        currency=plan.currency.code,
        name=plan.name,
        balance_minor=plan.balance.amount_minor,
        annual_rate_bps=plan.annual_rate_bps,
        frequency=plan.frequency.value,
        contribution_minor=plan.contribution.amount_minor,
        target_minor=plan.target_minor,
        target_date=plan.target_date,
        next_contribution_at=plan.next_contribution_at,
        last_accrual_at=plan.last_accrual_at,
        accrued_micro=plan.accrued_micro,
        status=plan.status.value,
        created_at=plan.created_at,
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


def merchant_to_domain(model: MerchantModel) -> Merchant:
    return Merchant(
        id=EntityId(model.id),
        user_id=EntityId(model.user_id),
        display_name=model.display_name,
        category=model.category,
        currency=Currency.of(model.currency),
        fee_bps=model.fee_bps,
        created_at=model.created_at,
        status=MerchantStatus(model.status),
    )


def merchant_to_model(merchant: Merchant) -> MerchantModel:
    return MerchantModel(
        id=str(merchant.id),
        user_id=str(merchant.user_id),
        display_name=merchant.display_name,
        category=merchant.category,
        currency=merchant.currency.code,
        fee_bps=merchant.fee_bps,
        status=merchant.status.value,
        created_at=merchant.created_at,
    )


def merchant_charge_to_domain(model: MerchantChargeModel) -> MerchantCharge:
    currency = Currency.of(model.currency)
    return MerchantCharge(
        id=EntityId(model.id),
        merchant_id=EntityId(model.merchant_id),
        amount=Money(model.amount_minor, currency),
        currency_code=model.currency,
        reference=model.reference,
        status=MerchantChargeStatus(model.status),
        created_at=model.created_at,
        expires_at=model.expires_at,
        paid_by=EntityId(model.paid_by) if model.paid_by else None,
        ledger_transaction_id=(
            EntityId(model.ledger_transaction_id) if model.ledger_transaction_id else None
        ),
    )


def merchant_charge_to_model(charge: MerchantCharge) -> MerchantChargeModel:
    return MerchantChargeModel(
        id=str(charge.id),
        merchant_id=str(charge.merchant_id),
        amount_minor=charge.amount.amount_minor,
        currency=charge.currency_code,
        reference=charge.reference,
        status=charge.status.value,
        created_at=charge.created_at,
        expires_at=charge.expires_at,
        paid_by=str(charge.paid_by) if charge.paid_by else None,
        ledger_transaction_id=(
            str(charge.ledger_transaction_id) if charge.ledger_transaction_id else None
        ),
    )


def merchant_payment_to_domain(model: MerchantPaymentModel) -> MerchantPayment:
    currency = Currency.of(model.currency)
    return MerchantPayment(
        id=EntityId(model.id),
        payer_id=EntityId(model.payer_id),
        merchant_id=EntityId(model.merchant_id),
        amount=Money(model.amount_minor, currency),
        fee=Money(model.fee_minor, currency),
        currency_code=model.currency,
        reference=model.reference,
        status=MerchantPaymentStatus(model.status),
        ledger_transaction_id=EntityId(model.ledger_transaction_id),
        created_at=model.created_at,
        charge_id=EntityId(model.charge_id) if model.charge_id else None,
    )


def merchant_payment_to_model(payment: MerchantPayment) -> MerchantPaymentModel:
    return MerchantPaymentModel(
        id=str(payment.id),
        payer_id=str(payment.payer_id),
        merchant_id=str(payment.merchant_id),
        charge_id=str(payment.charge_id) if payment.charge_id else None,
        amount_minor=payment.amount.amount_minor,
        fee_minor=payment.fee.amount_minor,
        currency=payment.currency_code,
        reference=payment.reference,
        status=payment.status.value,
        ledger_transaction_id=str(payment.ledger_transaction_id),
        created_at=payment.created_at,
    )


# --------------------------------------------------------------------- référentiel


def operator_to_domain(model: OperatorModel) -> Operator:
    prefixes = tuple(p for p in model.msisdn_prefixes.split(",") if p)
    return Operator(
        code=model.code,
        name=model.name,
        country=CountryCode(model.country_code),
        msisdn_prefixes=prefixes,
        active=model.active,
    )


def country_to_domain(model: CountryModel) -> Country:
    return Country(
        code=CountryCode(model.code),
        name=model.name,
        currency=Currency.of(model.currency),
        dialing_code=model.dialing_code,
        timezone=model.timezone,
        active=model.active,
        operators=tuple(operator_to_domain(o) for o in model.operators),
    )


def operator_to_model(operator: Operator) -> OperatorModel:
    return OperatorModel(
        code=operator.code,
        country_code=operator.country.value,
        name=operator.name,
        msisdn_prefixes=",".join(operator.msisdn_prefixes),
        active=operator.active,
    )


def country_to_models(country: Country) -> tuple[CountryModel, list[OperatorModel]]:
    operators = [
        OperatorModel(
            code=o.code,
            country_code=country.code.value,
            name=o.name,
            msisdn_prefixes=",".join(o.msisdn_prefixes),
            active=o.active,
        )
        for o in country.operators
    ]
    return (
        CountryModel(
            code=country.code.value,
            name=country.name,
            currency=country.currency.code,
            dialing_code=country.dialing_code,
            timezone=country.timezone,
            active=country.active,
        ),
        operators,
    )


# ------------------------------------------------------------------------- carte


def card_to_domain(model: CardModel) -> Card:
    currency = Currency.of(model.currency)
    channels = frozenset(CardChannel(c) for c in model.channels.split(",") if c)
    return Card(
        id=EntityId(model.id),
        wallet_id=EntityId(model.wallet_id),
        user_id=EntityId(model.user_id),
        currency=currency,
        network=CardNetwork(model.network),
        pan_token=model.pan_token,
        last4=model.last4,
        expiry_month=model.expiry_month,
        expiry_year=model.expiry_year,
        daily_limit=Money(model.daily_limit_minor, currency),
        monthly_limit=Money(model.monthly_limit_minor, currency),
        created_at=model.created_at,
        channels=channels,
        status=CardStatus(model.status),
    )


def card_to_model(card: Card) -> CardModel:
    return CardModel(
        id=str(card.id),
        wallet_id=str(card.wallet_id),
        user_id=str(card.user_id),
        currency=card.currency.code,
        network=card.network.value,
        pan_token=card.pan_token,
        last4=card.last4,
        expiry_month=card.expiry_month,
        expiry_year=card.expiry_year,
        status=card.status.value,
        daily_limit_minor=card.daily_limit.amount_minor,
        monthly_limit_minor=card.monthly_limit.amount_minor,
        channels=",".join(sorted(c.value for c in card.channels)),
        created_at=card.created_at,
    )


def card_authorization_to_domain(model: CardAuthorizationModel) -> CardAuthorization:
    currency = Currency.of(model.currency)
    return CardAuthorization(
        id=EntityId(model.id),
        card_id=EntityId(model.card_id),
        wallet_id=EntityId(model.wallet_id),
        user_id=EntityId(model.user_id),
        authorization_id=model.authorization_id,
        amount=Money(model.amount_minor, currency),
        currency_code=model.currency,
        channel=CardChannel(model.channel),
        status=CardAuthorizationStatus(model.status),
        created_at=model.created_at,
        merchant_name=model.merchant_name,
        decline_reason=model.decline_reason,
        resolved_at=model.resolved_at,
        captured_minor=model.captured_minor,
        ledger_transaction_id=(
            EntityId(model.ledger_transaction_id) if model.ledger_transaction_id else None
        ),
    )


def card_authorization_to_model(auth: CardAuthorization) -> CardAuthorizationModel:
    return CardAuthorizationModel(
        id=str(auth.id),
        card_id=str(auth.card_id),
        wallet_id=str(auth.wallet_id),
        user_id=str(auth.user_id),
        authorization_id=auth.authorization_id,
        amount_minor=auth.amount.amount_minor,
        currency=auth.currency_code,
        channel=auth.channel.value,
        merchant_name=auth.merchant_name,
        status=auth.status.value,
        decline_reason=auth.decline_reason,
        created_at=auth.created_at,
        resolved_at=auth.resolved_at,
        captured_minor=auth.captured_minor,
        ledger_transaction_id=(
            str(auth.ledger_transaction_id) if auth.ledger_transaction_id else None
        ),
    )


def operator_transfer_to_domain(model: OperatorTransferModel) -> OperatorTransfer:
    currency = Currency.of(model.currency)
    return OperatorTransfer(
        id=EntityId(model.id),
        user_id=EntityId(model.user_id),
        wallet_id=EntityId(model.wallet_id),
        operator=model.operator,
        direction=OperatorTransferDirection(model.direction),
        msisdn=Msisdn(model.msisdn),
        amount=Money(model.amount_minor, currency),
        fee=Money(model.fee_minor, currency),
        reference=model.reference,
        status=OperatorTransferStatus(model.status),
        created_at=model.created_at,
        currency_code=model.currency,
        external_ref=model.external_ref,
        failure_reason=model.failure_reason,
        resolved_at=model.resolved_at,
        ledger_transaction_id=(
            EntityId(model.ledger_transaction_id) if model.ledger_transaction_id else None
        ),
    )


def operator_transfer_to_model(transfer: OperatorTransfer) -> OperatorTransferModel:
    return OperatorTransferModel(
        id=str(transfer.id),
        user_id=str(transfer.user_id),
        wallet_id=str(transfer.wallet_id),
        operator=transfer.operator,
        direction=transfer.direction.value,
        msisdn=transfer.msisdn.value,
        amount_minor=transfer.amount.amount_minor,
        fee_minor=transfer.fee.amount_minor,
        currency=transfer.currency_code,
        reference=transfer.reference,
        external_ref=transfer.external_ref,
        status=transfer.status.value,
        failure_reason=transfer.failure_reason,
        created_at=transfer.created_at,
        resolved_at=transfer.resolved_at,
        ledger_transaction_id=(
            str(transfer.ledger_transaction_id) if transfer.ledger_transaction_id else None
        ),
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
    "card_authorization_to_domain",
    "card_authorization_to_model",
    "card_to_domain",
    "card_to_model",
    "cash_order_to_domain",
    "cash_order_to_model",
    "country_to_domain",
    "country_to_models",
    "kyc_case_to_domain",
    "kyc_case_to_model",
    "ledger_transaction_to_domain",
    "ledger_transaction_to_model",
    "merchant_charge_to_domain",
    "merchant_charge_to_model",
    "merchant_payment_to_domain",
    "merchant_payment_to_model",
    "merchant_to_domain",
    "merchant_to_model",
    "operator_to_model",
    "operator_transfer_to_domain",
    "operator_transfer_to_model",
    "payment_request_to_domain",
    "payment_request_to_model",
    "savings_plan_to_domain",
    "savings_plan_to_model",
    "user_to_domain",
    "user_to_model",
    "vault_pockets_to_models",
    "vault_to_domain",
    "wallet_to_domain",
    "wallet_to_model",
]
