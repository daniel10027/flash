"""Tests de l'agrégat Agent (BE-034)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest

from flash.domain.agent.agent import Agent, AgentStatus
from flash.domain.shared.errors import AgentFloatTooLow, InvalidAccountState
from flash.domain.shared.identifiers import EntityId
from flash.domain.shared.money import XOF, Currency, Money

T0 = datetime(2026, 1, 1, tzinfo=UTC)
AID = EntityId(str(UUID(int=1)))
UID = EntityId(str(UUID(int=2)))


def _agent(*, available: int = 0, cap: int = 1_000_000, bps: int = 100) -> Agent:
    return Agent(
        id=AID,
        user_id=UID,
        currency=XOF,
        float_available=Money(available, XOF),
        float_cap=Money(cap, XOF),
        commission_bps=bps,
        created_at=T0,
    )


class TestConstruction:
    def test_enroll_records_event(self) -> None:
        agent = Agent.enroll(
            agent_id=AID,
            user_id=UID,
            currency=XOF,
            float_cap=Money(500_000, XOF),
            commission_bps=100,
            now=T0,
        )
        assert agent.float_available == Money(0, XOF)
        assert [e.name for e in agent.pull_events()] == ["AgentEnrolled"]

    def test_wrong_currency_rejected(self) -> None:
        with pytest.raises(ValueError, match="devise"):
            Agent(
                id=AID,
                user_id=UID,
                currency=XOF,
                float_available=Money(0, Currency.of("EUR")),
                float_cap=Money(1, XOF),
                commission_bps=0,
                created_at=T0,
            )

    def test_negative_float_rejected(self) -> None:
        with pytest.raises(ValueError, match="négatif"):
            _agent(available=-1)

    @pytest.mark.parametrize("bps", [-1, 2001])
    def test_commission_out_of_bounds_rejected(self, bps: int) -> None:
        with pytest.raises(ValueError, match="commission_bps"):
            _agent(bps=bps)


class TestMovements:
    def test_disburse_reduces_float(self) -> None:
        agent = _agent(available=100_000)
        agent.disburse_float(Money(30_000, XOF), T0)
        assert agent.float_available == Money(70_000, XOF)
        assert [e.name for e in agent.pull_events()] == ["AgentFloatDisbursed"]

    def test_disburse_beyond_float_rejected(self) -> None:
        with pytest.raises(AgentFloatTooLow):
            _agent(available=1_000).disburse_float(Money(5_000, XOF), T0)

    def test_collect_grows_float_within_cap(self) -> None:
        agent = _agent(available=0, cap=50_000)
        agent.collect_float(Money(50_000, XOF), T0)
        assert agent.float_available == Money(50_000, XOF)

    def test_collect_beyond_cap_rejected(self) -> None:
        with pytest.raises(AgentFloatTooLow, match="Plafond"):
            _agent(available=40_000, cap=50_000).collect_float(Money(20_000, XOF), T0)

    def test_commission_floors(self) -> None:
        # 1 % de 12 345 = 123,45 -> 123
        assert _agent(bps=100).commission_for(Money(12_345, XOF)) == Money(123, XOF)

    def test_movements_guard_currency_and_positivity(self) -> None:
        agent = _agent(available=1_000)
        with pytest.raises(ValueError, match="strictement positif"):
            agent.disburse_float(Money(0, XOF), T0)
        with pytest.raises(ValueError, match="Devise"):
            agent.collect_float(Money(1, Currency.of("EUR")), T0)

    def test_suspended_agent_blocks_movements(self) -> None:
        agent = _agent(available=100_000)
        agent.suspend("contrôle", T0)
        assert agent.status is AgentStatus.SUSPENDED
        with pytest.raises(InvalidAccountState):
            agent.disburse_float(Money(1_000, XOF), T0)
        assert "AgentSuspended" in [e.name for e in agent.pull_events()]

    def test_suspend_is_idempotent(self) -> None:
        agent = _agent()
        agent.suspend("x", T0)
        agent.pull_events()
        agent.suspend("x", T0)
        assert agent.pull_events() == []

    def test_accrue_commission_records_event(self) -> None:
        agent = _agent()
        agent.accrue_commission(Money(300, XOF), T0)
        assert [e.name for e in agent.pull_events()] == ["AgentCommissionAccrued"]

    def test_repr(self) -> None:
        assert "float=" in repr(_agent(available=5, cap=10))
