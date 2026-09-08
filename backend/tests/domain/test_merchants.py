"""Tests des agrégats marchands : Merchant, MerchantCharge, MerchantPayment (BE-033)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from flash.domain.merchants.charge import MerchantCharge, MerchantChargeStatus
from flash.domain.merchants.merchant import Merchant, MerchantStatus
from flash.domain.merchants.payment import MerchantPayment, MerchantPaymentStatus
from flash.domain.shared.errors import InvalidAccountState, InvalidInput
from flash.domain.shared.identifiers import EntityId
from flash.domain.shared.money import XOF, Currency, Money

T0 = datetime(2026, 1, 1, tzinfo=UTC)
MID = EntityId(str(UUID(int=1)))
UID = EntityId(str(UUID(int=2)))
PAYER = EntityId(str(UUID(int=3)))
CHARGE = EntityId(str(UUID(int=4)))
TXN = EntityId(str(UUID(int=5)))


def _merchant(*, fee_bps: int = 100, status: MerchantStatus = MerchantStatus.ACTIVE) -> Merchant:
    return Merchant(
        id=MID,
        user_id=UID,
        display_name="Chez Awa",
        category="RESTAURANT",
        currency=XOF,
        fee_bps=fee_bps,
        created_at=T0,
        status=status,
    )


class TestMerchant:
    def test_enroll_records_event_and_static_qr(self) -> None:
        merchant = Merchant.enroll(
            merchant_id=MID,
            user_id=UID,
            display_name="  Chez Awa  ",
            category="",
            currency=XOF,
            fee_bps=100,
            now=T0,
        )
        assert merchant.display_name == "Chez Awa"
        assert merchant.category == "GENERAL"
        assert merchant.static_qr_payload() == f"flash://pay?m={MID}"
        assert [e.name for e in merchant.pull_events()] == ["MerchantEnrolled"]

    def test_blank_name_rejected(self) -> None:
        with pytest.raises(ValueError, match="nom commercial"):
            _merchant_with_name("   ")

    @pytest.mark.parametrize("bps", [-1, 1001])
    def test_fee_bps_out_of_bounds_rejected(self, bps: int) -> None:
        with pytest.raises(ValueError, match="fee_bps"):
            _merchant(fee_bps=bps)

    def test_fee_for_floors(self) -> None:
        # 1 % de 12 345 = 123,45 -> 123
        assert _merchant(fee_bps=100).fee_for(Money(12_345, XOF)) == Money(123, XOF)

    def test_fee_for_wrong_currency_rejected(self) -> None:
        with pytest.raises(ValueError, match="Devise"):
            _merchant().fee_for(Money(1, Currency.of("EUR")))

    def test_suspended_merchant_blocks(self) -> None:
        merchant = _merchant()
        merchant.suspend("fraude", T0)
        assert merchant.status is MerchantStatus.SUSPENDED
        with pytest.raises(InvalidAccountState):
            merchant.ensure_active()
        merchant.suspend("encore", T0)  # idempotent
        assert [e.name for e in merchant.pull_events()] == ["MerchantSuspended"]

    def test_repr(self) -> None:
        assert "fee_bps=100" in repr(_merchant())


def _merchant_with_name(name: str) -> Merchant:
    return Merchant(
        id=MID,
        user_id=UID,
        display_name=name,
        category="X",
        currency=XOF,
        fee_bps=0,
        created_at=T0,
    )


def _charge(*, amount: int = 25_000, expires_in: int = 60) -> MerchantCharge:
    return MerchantCharge.open(
        charge_id=CHARGE,
        merchant_id=MID,
        amount=Money(amount, XOF),
        reference="Table 4",
        now=T0,
        expires_at=T0 + timedelta(minutes=expires_in),
    )


class TestMerchantCharge:
    def test_open_is_pending_with_dynamic_qr(self) -> None:
        charge = _charge()
        assert charge.status is MerchantChargeStatus.PENDING
        assert charge.dynamic_qr_payload() == f"flash://pay?m={MID}&c={CHARGE}"
        assert [e.name for e in charge.pull_events()] == ["MerchantChargeOpened"]

    def test_blank_reference_rejected(self) -> None:
        with pytest.raises(InvalidInput, match="référence"):
            MerchantCharge.open(
                charge_id=CHARGE,
                merchant_id=MID,
                amount=Money(1, XOF),
                reference="  ",
                now=T0,
                expires_at=T0 + timedelta(minutes=1),
            )

    def test_non_positive_amount_rejected(self) -> None:
        with pytest.raises(ValueError, match="strictement positif"):
            MerchantCharge(
                id=CHARGE,
                merchant_id=MID,
                amount=Money(0, XOF),
                currency_code="XOF",
                reference="r",
                status=MerchantChargeStatus.PENDING,
                created_at=T0,
                expires_at=T0,
            )

    def test_currency_mismatch_rejected(self) -> None:
        with pytest.raises(ValueError, match="Devise incohérente"):
            MerchantCharge(
                id=CHARGE,
                merchant_id=MID,
                amount=Money(1, Currency.of("EUR")),
                currency_code="XOF",
                reference="r",
                status=MerchantChargeStatus.PENDING,
                created_at=T0,
                expires_at=T0,
            )

    def test_repr(self) -> None:
        assert "status=PENDING" in repr(_charge())

    def test_ensure_payable_guards_status_and_expiry(self) -> None:
        charge = _charge()
        charge.ensure_payable(T0)  # ok
        with pytest.raises(InvalidAccountState, match="expiré"):
            charge.ensure_payable(T0 + timedelta(minutes=90))

    def test_mark_paid_transitions(self) -> None:
        charge = _charge()
        charge.pull_events()
        charge.mark_paid(payer_id=PAYER, ledger_transaction_id=TXN)
        assert charge.status is MerchantChargeStatus.PAID
        assert charge.paid_by == PAYER
        with pytest.raises(InvalidAccountState):
            charge.ensure_payable(T0)

    def test_cancel_and_expire(self) -> None:
        charge = _charge()
        charge.pull_events()
        charge.cancel(T0)
        assert charge.status is MerchantChargeStatus.CANCELLED
        assert [e.name for e in charge.pull_events()] == ["MerchantChargeCancelled"]
        with pytest.raises(InvalidAccountState):
            charge.cancel(T0)

        other = _charge()
        other.pull_events()
        other.expire(T0)
        assert other.status is MerchantChargeStatus.EXPIRED
        assert [e.name for e in other.pull_events()] == ["MerchantChargeExpired"]
        other.expire(T0)  # no-op
        assert other.pull_events() == []


class TestMerchantPayment:
    def test_record_is_completed_with_event(self) -> None:
        payment = MerchantPayment.record(
            payment_id=EntityId(str(UUID(int=9))),
            payer_id=PAYER,
            merchant_id=MID,
            amount=Money(25_000, XOF),
            fee=Money(250, XOF),
            reference="Table 4",
            ledger_transaction_id=TXN,
            now=T0,
            charge_id=CHARGE,
        )
        assert payment.status is MerchantPaymentStatus.COMPLETED
        assert payment.net_to_merchant == Money(24_750, XOF)
        assert [e.name for e in payment.pull_events()] == ["MerchantPaymentCompleted"]

    def test_fee_greater_than_amount_rejected(self) -> None:
        with pytest.raises(ValueError, match="Commission marchand"):
            _payment(fee=Money(200, XOF))

    def test_currency_mismatch_rejected(self) -> None:
        with pytest.raises(ValueError, match="Devises incohérentes"):
            _payment(amount=Money(100, Currency.of("EUR")))

    def test_non_positive_amount_rejected(self) -> None:
        with pytest.raises(ValueError, match="strictement positif"):
            _payment(amount=Money(0, XOF), fee=Money(0, XOF))

    def test_repr(self) -> None:
        assert "status=COMPLETED" in repr(_payment())


def _payment(*, amount: Money | None = None, fee: Money | None = None) -> MerchantPayment:
    return MerchantPayment(
        id=EntityId(str(UUID(int=9))),
        payer_id=PAYER,
        merchant_id=MID,
        amount=amount if amount is not None else Money(100, XOF),
        fee=fee if fee is not None else Money(10, XOF),
        currency_code="XOF",
        reference="r",
        status=MerchantPaymentStatus.COMPLETED,
        ledger_transaction_id=TXN,
        created_at=T0,
    )
