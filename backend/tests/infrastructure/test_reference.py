"""Tests unitaires du référentiel infra (BE-061) et de la grille multi-pays (BE-063)."""

from __future__ import annotations

from typing import Any

from flash.domain.identity.kyc import KycTier
from flash.domain.pricing.pricing import PricingService
from flash.domain.shared.identifiers import CountryCode, Msisdn
from flash.domain.shared.money import Currency, Money
from flash.domain.shared.operations import OperationType
from flash.infrastructure.limits import build_limit_repository
from flash.infrastructure.pricing import build_pricing_repository
from flash.infrastructure.reference import (
    CachingReferenceDirectory,
    StaticReferenceDirectory,
    _static_countries,
)

XOF = Currency.of("XOF")
XAF = Currency.of("XAF")


class _FakeRedis:
    def __init__(self) -> None:
        self._v = 0
        self.get_calls = 0

    def get(self, key: str) -> bytes | None:
        self.get_calls += 1
        return str(self._v).encode() if self._v else None

    def incr(self, key: str) -> int:
        self._v += 1
        return self._v


class _CountingDirectory(StaticReferenceDirectory):
    def __init__(self) -> None:
        super().__init__()
        self.loads = 0

    def _all(self) -> Any:
        self.loads += 1
        return super()._all()


class TestStaticDirectory:
    def test_covers_uemoa_and_cemac(self) -> None:
        d = StaticReferenceDirectory()
        codes = {c.code.value for c in d.countries()}
        assert {"CI", "SN", "ML", "BF", "BJ", "TG", "NE", "GW", "CM", "GA"} == codes
        assert d.currency_for(CountryCode("CI")) == XOF
        assert d.currency_for(CountryCode("CM")) == XAF

    def test_operator_lookup_by_msisdn(self) -> None:
        d = StaticReferenceDirectory()
        assert d.operator_for_msisdn(Msisdn("+2250712345678")).code == "ORANGE_CI"  # type: ignore[union-attr]
        assert d.operator_for_msisdn(Msisdn("+221771234567")).code == "ORANGE_SN"  # type: ignore[union-attr]

    def test_dataset_builder_is_valid(self) -> None:
        assert len(_static_countries()) == 10  # les VOs valident à la construction


class TestCachingDirectory:
    def test_serves_snapshot_and_reloads_on_version_bump(self) -> None:
        redis = _FakeRedis()
        inner = _CountingDirectory()
        cache = CachingReferenceDirectory(inner, redis)  # type: ignore[arg-type]

        cache.countries()
        cache.countries()
        assert inner.loads == 1  # instantané réutilisé

        cache.bump()  # un autre worker a modifié le référentiel
        cache.countries()
        assert inner.loads == 2  # rechargé

    def test_reload_forces_local_refresh(self) -> None:
        redis = _FakeRedis()
        inner = _CountingDirectory()
        cache = CachingReferenceDirectory(inner, redis)  # type: ignore[arg-type]
        cache.reload()
        cache.reload()
        assert inner.loads == 2


class TestPricingGridMultiCountry:
    def _svc(self) -> PricingService:
        return PricingService(build_pricing_repository())

    def test_transfer_fee_differs_by_country(self) -> None:
        svc = self._svc()
        ci = svc.fee_for(
            country=CountryCode("CI"), operation=OperationType.TRANSFER, amount=Money(100_000, XOF)
        )
        sn = svc.fee_for(
            country=CountryCode("SN"), operation=OperationType.TRANSFER, amount=Money(100_000, XOF)
        )
        assert ci.total == Money(800, XOF)  # 0,8 %
        assert sn.total == Money(1_000, XOF)  # 1,0 % — preuve de généricité

    def test_transfer_fee_in_xaf_for_cemac(self) -> None:
        fee = self._svc().fee_for(
            country=CountryCode("CM"), operation=OperationType.TRANSFER, amount=Money(100_000, XAF)
        )
        assert fee.total == Money(900, XAF)  # 0,9 % en XAF

    def test_merchant_payment_is_free_everywhere(self) -> None:
        svc = self._svc()
        for code in ("CI", "SN", "GA"):
            currency = XAF if code == "GA" else XOF
            fee = svc.fee_for(
                country=CountryCode(code),
                operation=OperationType.MERCHANT_PAYMENT,
                amount=Money(50_000, currency),
            )
            assert fee.is_zero


class TestLimitGridMultiCurrency:
    def test_caps_use_country_currency(self) -> None:
        repo = build_limit_repository()
        rule_ci = repo.rule_for(CountryCode("CI"), KycTier.TIER_0, OperationType.TRANSFER)
        rule_cm = repo.rule_for(CountryCode("CM"), KycTier.TIER_0, OperationType.TRANSFER)
        assert rule_ci is not None and rule_ci.per_tx == Money(200_000, XOF)
        assert rule_cm is not None and rule_cm.per_tx == Money(200_000, XAF)
