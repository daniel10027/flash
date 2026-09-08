"""Tests des primitives d'événements de domaine (BE-006)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, dataclass
from datetime import UTC, datetime

import pytest

from flash.domain.shared.events import DomainEvent, EventRecorder


@dataclass(frozen=True, slots=True, kw_only=True)
class MoneySent(DomainEvent):
    amount_minor: int
    currency: str


class Wallet(EventRecorder):
    def __init__(self) -> None:
        super().__init__()

    def send(self) -> None:
        self.record_event(
            MoneySent(
                occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
                aggregate_id="w-1",
                amount_minor=1000,
                currency="XOF",
            )
        )


class TestDomainEvent:
    def test_name_is_class_name(self) -> None:
        event = MoneySent(
            occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
            aggregate_id="w-1",
            amount_minor=1000,
            currency="XOF",
        )
        assert event.name == "MoneySent"

    def test_to_payload_serialises_datetime_and_fields(self) -> None:
        event = MoneySent(
            occurred_at=datetime(2026, 1, 1, 12, 30, tzinfo=UTC),
            aggregate_id="w-1",
            amount_minor=1000,
            currency="XOF",
        )
        assert event.to_payload() == {
            "occurred_at": "2026-01-01T12:30:00+00:00",
            "aggregate_id": "w-1",
            "amount_minor": 1000,
            "currency": "XOF",
        }

    def test_event_is_immutable(self) -> None:
        event = MoneySent(
            occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
            aggregate_id="w-1",
            amount_minor=1000,
            currency="XOF",
        )
        with pytest.raises(FrozenInstanceError):
            event.amount_minor = 2  # type: ignore[misc]


class TestEventRecorder:
    def test_pull_events_returns_and_clears(self) -> None:
        wallet = Wallet()
        wallet.send()
        wallet.send()

        first = wallet.pull_events()
        assert [e.name for e in first] == ["MoneySent", "MoneySent"]
        assert wallet.pull_events() == []

    def test_events_start_empty(self) -> None:
        assert Wallet().pull_events() == []
