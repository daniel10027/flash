"""Cas d'usage de l'espace agent (BE-072/073/074)."""

from __future__ import annotations

from uuid import UUID

import pytest

from flash.application.agent.operations import (
    AgentFloatCommand,
    AttachAgentToMaster,
    AttachAgentToMasterCommand,
    GetAgentOverview,
    GetAgentOverviewCommand,
    ListAgentOperations,
    ListAgentOperationsCommand,
    LookupCustomer,
    LookupCustomerCommand,
    PayAgentCommission,
    PayAgentCommissionCommand,
    TopUpAgentFloat,
    WithdrawAgentFloat,
)
from flash.application.cash.operations import NotAnAgent
from flash.application.services import AppServices
from flash.domain.agent.agent import Agent
from flash.domain.cash.order import CashOrder
from flash.domain.identity.pin import Pin
from flash.domain.identity.user import User
from flash.domain.shared.errors import AgentFloatTooLow, InvalidInput
from flash.domain.shared.identifiers import CountryCode, EntityId, Msisdn
from flash.domain.shared.money import XOF, Money
from flash.domain.wallet.wallet import Wallet
from tests.support.fakes import (
    FakePinHasher,
    FixedClock,
    InMemoryIdempotencyStore,
    RecordingEventPublisher,
    SeqIdGenerator,
)
from tests.support.repositories import InMemoryUnitOfWork

CI = CountryCode("CI")
AGENT_ID = EntityId(str(UUID(int=7)))
AGENT_UID = str(UUID(int=7))
AGENT_MSISDN = "+2250700000007"


@pytest.fixture
def uow() -> InMemoryUnitOfWork:
    return InMemoryUnitOfWork()


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock()


@pytest.fixture
def services(uow: InMemoryUnitOfWork, clock: FixedClock) -> AppServices:
    return AppServices(
        uow=lambda: uow,
        clock=clock,
        ids=SeqIdGenerator(),
        events=RecordingEventPublisher(),
        idempotency=InMemoryIdempotencyStore(),
    )


def _agent(
    uow: InMemoryUnitOfWork,
    *,
    float_available: int = 0,
    cap: int = 5_000_000,
    earned: int = 0,
    paid: int = 0,
) -> Agent:
    user = User.register(
        user_id=EntityId(AGENT_UID),
        country=CI,
        msisdn=Msisdn(AGENT_MSISDN),
        pin_hash=FakePinHasher().hash(Pin("1397")),
        now=FixedClock().now(),
    )
    user.activate(FixedClock().now())
    user.pull_events()
    uow.users.add(user)
    wallet = Wallet.open(
        wallet_id=EntityId(str(UUID(int=507))),
        user_id=user.id,
        currency=XOF,
        now=FixedClock().now(),
    )
    wallet.pull_events()
    uow.wallets.add(wallet)
    agent = Agent(
        id=AGENT_ID,
        user_id=user.id,
        currency=XOF,
        float_available=Money(float_available, XOF),
        float_cap=Money(cap, XOF),
        commission_bps=100,
        created_at=FixedClock().now(),
        commission_earned=Money(earned, XOF),
        commission_paid=Money(paid, XOF),
    )
    uow.agents.add(agent)
    return agent


class TestFloatMoves:
    def test_topup_raises_float_and_writes_ledger(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _agent(uow, float_available=100_000)
        receipt = TopUpAgentFloat(services=services).execute(
            AgentFloatCommand(
                agent_user_id=AGENT_UID, amount_minor=400_000, idempotency_key="agent-topup-1"
            )
        )
        assert receipt.direction == "topup"
        assert receipt.float_available_after_minor == 500_000
        assert len(uow.ledger.transactions) == 1

    def test_topup_is_idempotent(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _agent(uow, float_available=100_000)
        cmd = AgentFloatCommand(
            agent_user_id=AGENT_UID, amount_minor=400_000, idempotency_key="agent-topup-rep"
        )
        first = TopUpAgentFloat(services=services).execute(cmd)
        second = TopUpAgentFloat(services=services).execute(cmd)
        assert first.to_dict() == second.to_dict()
        agent = uow.agents.get(AGENT_ID)
        assert agent is not None and agent.float_available == Money(500_000, XOF)

    def test_withdraw_lowers_float(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _agent(uow, float_available=500_000)
        receipt = WithdrawAgentFloat(services=services).execute(
            AgentFloatCommand(
                agent_user_id=AGENT_UID, amount_minor=200_000, idempotency_key="agent-wd-1"
            )
        )
        assert receipt.float_available_after_minor == 300_000

    def test_withdraw_over_float_rejected(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _agent(uow, float_available=100_000)
        with pytest.raises(AgentFloatTooLow):
            WithdrawAgentFloat(services=services).execute(
                AgentFloatCommand(
                    agent_user_id=AGENT_UID, amount_minor=200_000, idempotency_key="agent-wd-x"
                )
            )

    def test_non_positive_amount_rejected(self, services: AppServices) -> None:
        with pytest.raises(InvalidInput):
            TopUpAgentFloat(services=services).execute(
                AgentFloatCommand(
                    agent_user_id=AGENT_UID, amount_minor=0, idempotency_key="agent-zero"
                )
            )

    def test_bad_idempotency_key_rejected(self, services: AppServices) -> None:
        with pytest.raises(InvalidInput):
            TopUpAgentFloat(services=services).execute(
                AgentFloatCommand(agent_user_id=AGENT_UID, amount_minor=1_000, idempotency_key="x")
            )

    def test_non_agent_rejected(self, services: AppServices) -> None:
        with pytest.raises(NotAnAgent):
            TopUpAgentFloat(services=services).execute(
                AgentFloatCommand(
                    agent_user_id=AGENT_UID, amount_minor=1_000, idempotency_key="agent-noagent"
                )
            )


class TestCommissionPayout:
    def test_pays_full_owed_to_wallet(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _agent(uow, float_available=10_000, earned=3_000, paid=0)
        view = PayAgentCommission(services=services).execute(
            PayAgentCommissionCommand(agent_user_id=AGENT_UID)
        )
        assert view.commission_paid_minor == 3_000
        assert view.commission_owed_minor == 0
        assert view.float_available_minor == 7_000
        wallet = uow.wallets.get(EntityId(str(UUID(int=507))))
        assert wallet is not None and wallet.available == Money(3_000, XOF)
        [txn] = uow.ledger.transactions
        assert txn.kind.value == "AGENT_COMMISSION_PAYOUT"

    def test_pays_partial_amount(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _agent(uow, float_available=10_000, earned=3_000)
        view = PayAgentCommission(services=services).execute(
            PayAgentCommissionCommand(agent_user_id=AGENT_UID, amount_minor=1_000)
        )
        assert view.commission_owed_minor == 2_000

    def test_nothing_owed_rejected(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _agent(uow, float_available=10_000, earned=0)
        with pytest.raises(InvalidInput, match="Aucune commission"):
            PayAgentCommission(services=services).execute(
                PayAgentCommissionCommand(agent_user_id=AGENT_UID)
            )

    def test_more_than_owed_rejected(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _agent(uow, float_available=10_000, earned=1_000)
        with pytest.raises(InvalidInput):
            PayAgentCommission(services=services).execute(
                PayAgentCommissionCommand(agent_user_id=AGENT_UID, amount_minor=5_000)
            )

    def test_float_too_low_rejected(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _agent(uow, float_available=500, earned=3_000)
        with pytest.raises(AgentFloatTooLow):
            PayAgentCommission(services=services).execute(
                PayAgentCommissionCommand(agent_user_id=AGENT_UID)
            )


class TestHierarchy:
    def test_attach_to_master(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _agent(uow)
        master = Agent(
            id=EntityId(str(UUID(int=8))),
            user_id=EntityId(str(UUID(int=80))),
            currency=XOF,
            float_available=Money(0, XOF),
            float_cap=Money(1_000_000, XOF),
            commission_bps=50,
            created_at=FixedClock().now(),
        )
        uow.agents.add(master)
        view = AttachAgentToMaster(services=services).execute(
            AttachAgentToMasterCommand(agent_id=str(AGENT_ID), master_agent_id=str(master.id))
        )
        assert view.parent_agent_id == str(master.id)

    def test_unknown_agent_rejected(self, services: AppServices) -> None:
        with pytest.raises(InvalidInput, match="introuvable"):
            AttachAgentToMaster(services=services).execute(
                AttachAgentToMasterCommand(
                    agent_id=str(UUID(int=404)), master_agent_id=str(UUID(int=405))
                )
            )

    def test_malformed_id_rejected(self, services: AppServices) -> None:
        with pytest.raises(InvalidInput, match="introuvable"):
            AttachAgentToMaster(services=services).execute(
                AttachAgentToMasterCommand(agent_id="bad", master_agent_id="worse")
            )


class TestReads:
    def test_overview(self, services: AppServices, uow: InMemoryUnitOfWork) -> None:
        _agent(uow, float_available=100_000, earned=2_000, paid=500)
        view = GetAgentOverview(services=services).execute(
            GetAgentOverviewCommand(agent_user_id=AGENT_UID)
        )
        assert view.commission_owed_minor == 1_500
        assert view.to_dict()["float_available_minor"] == 100_000

    def test_overview_non_agent_rejected(self, services: AppServices) -> None:
        with pytest.raises(NotAnAgent):
            GetAgentOverview(services=services).execute(
                GetAgentOverviewCommand(agent_user_id=AGENT_UID)
            )

    def test_list_operations(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _agent(uow)
        order = CashOrder.deposit(
            order_id=EntityId(str(UUID(int=200))),
            client_id=EntityId(str(UUID(int=3))),
            agent_id=AGENT_ID,
            amount=Money(25_000, XOF),
            ledger_transaction_id=EntityId(str(UUID(int=201))),
            now=FixedClock().now(),
        )
        order.pull_events()
        uow.cash_orders.add(order)
        lines = ListAgentOperations(services=services).execute(
            ListAgentOperationsCommand(agent_user_id=AGENT_UID, limit=500)
        )
        assert len(lines) == 1
        assert lines[0].type == "DEPOSIT"
        assert lines[0].to_dict()["amount_minor"] == 25_000

    def test_lookup_customer(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _agent(uow)
        client = User.register(
            user_id=EntityId(str(UUID(int=3))),
            country=CI,
            msisdn=Msisdn("+2250700000003"),
            pin_hash=FakePinHasher().hash(Pin("1397")),
            now=FixedClock().now(),
        )
        client.activate(FixedClock().now())
        client.pull_events()
        uow.users.add(client)
        view = LookupCustomer(services=services).execute(
            LookupCustomerCommand(
                agent_user_id=AGENT_UID, phone_number="+2250700000003", country="CI"
            )
        )
        assert view.user_id == str(UUID(int=3))
        assert view.msisdn_masked != "+2250700000003"
        assert view.to_dict()["kyc_tier"] == view.kyc_tier

    def test_lookup_unknown_customer_rejected(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _agent(uow)
        with pytest.raises(InvalidInput, match="Aucun client"):
            LookupCustomer(services=services).execute(
                LookupCustomerCommand(
                    agent_user_id=AGENT_UID, phone_number="+2250799999999", country="CI"
                )
            )

    def test_lookup_bad_number_rejected(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _agent(uow)
        with pytest.raises(InvalidInput):
            LookupCustomer(services=services).execute(
                LookupCustomerCommand(
                    agent_user_id=AGENT_UID, phone_number="not-a-number", country="CI"
                )
            )
