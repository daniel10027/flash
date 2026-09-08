"""Tests de la base applicative : UseCase, execute_in_uow, IdempotencyGuard (BE-015/016)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

import pytest

from flash.application.idempotency import IdempotencyGuard, IdempotencyOutcome
from flash.application.transaction import execute_in_uow
from flash.application.use_case import Command, UseCase
from flash.domain.identity.user import User
from flash.domain.shared.errors import DuplicateOperation
from flash.domain.shared.identifiers import CountryCode, EntityId, IdempotencyKey, Msisdn
from flash.domain.shared.money import XOF
from flash.domain.wallet.wallet import Wallet
from tests.support.fakes import InMemoryIdempotencyStore, RecordingEventPublisher
from tests.support.repositories import InMemoryUnitOfWork

T0 = datetime(2026, 1, 1, tzinfo=UTC)
USER_ID = EntityId(UUID(int=1))
KEY = IdempotencyKey("abc12345")


class TestUseCaseContract:
    def test_cannot_instantiate_abstract_use_case(self) -> None:
        with pytest.raises(TypeError):
            UseCase()  # type: ignore[abstract]

    def test_concrete_use_case_runs(self) -> None:
        @dataclass(frozen=True, slots=True)
        class Ping(Command):
            value: int

        class Echo(UseCase[Ping, int]):
            def execute(self, command: Ping) -> int:
                return command.value * 2

        assert Echo().execute(Ping(21)) == 42


class TestExecuteInUow:
    def _uow_factory(self, uow: InMemoryUnitOfWork) -> Callable[[], InMemoryUnitOfWork]:
        return lambda: uow

    def test_commits_and_publishes_collected_events(self) -> None:
        uow = InMemoryUnitOfWork()
        events = RecordingEventPublisher()

        def work(u: InMemoryUnitOfWork) -> str:
            user = User.register(
                user_id=USER_ID,
                country=CountryCode("CI"),
                msisdn=Msisdn("+2250700000001"),
                pin_hash="hashed:1397",
                now=T0,
            )
            u.users.add(user)
            wallet = Wallet.open(
                wallet_id=EntityId(UUID(int=2)), user_id=USER_ID, currency=XOF, now=T0
            )
            u.wallets.add(wallet)
            return "done"

        result = execute_in_uow(self._uow_factory(uow), events, work)

        assert result == "done"
        assert uow.committed
        assert events.names() == ["UserRegistered", "WalletOpened"]

    def test_exception_rolls_back_and_publishes_nothing(self) -> None:
        uow = InMemoryUnitOfWork()
        events = RecordingEventPublisher()

        def work(u: InMemoryUnitOfWork) -> None:
            u.users.add(
                User.register(
                    user_id=USER_ID,
                    country=CountryCode("CI"),
                    msisdn=Msisdn("+2250700000001"),
                    pin_hash="hashed:1397",
                    now=T0,
                )
            )
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError, match="boom"):
            execute_in_uow(self._uow_factory(uow), events, work)

        assert uow.rolled_back
        assert not uow.committed
        assert events.published == []

    def test_commits_even_when_no_events_collected(self) -> None:
        uow = InMemoryUnitOfWork()
        events = RecordingEventPublisher()

        result = execute_in_uow(self._uow_factory(uow), events, lambda _u: 7)

        assert result == 7
        assert uow.committed
        assert events.published == []


class TestIdempotencyGuard:
    def _guard(self) -> tuple[IdempotencyGuard, InMemoryIdempotencyStore]:
        store = InMemoryIdempotencyStore()
        return IdempotencyGuard(store, ttl_seconds=60), store

    def test_first_call_executes_and_stores(self) -> None:
        guard, _ = self._guard()
        calls = []

        def produce() -> tuple[str, dict[str, str]]:
            calls.append(1)
            return "RESULT", {"value": "RESULT"}

        outcome = guard.run(
            key=KEY,
            subject=str(USER_ID),
            route="POST /v1/transfers",
            produce=produce,
            rebuild=lambda d: d["value"],
        )
        assert outcome == IdempotencyOutcome(result="RESULT", replayed=False)
        assert calls == [1]

    def test_replay_returns_cached_without_reexecuting(self) -> None:
        guard, _ = self._guard()
        calls = []

        def produce() -> tuple[str, dict[str, str]]:
            calls.append(1)
            return "RESULT", {"value": "RESULT"}

        def call() -> IdempotencyOutcome[str]:
            return guard.run(
                key=KEY,
                subject=str(USER_ID),
                route="POST /v1/transfers",
                produce=produce,
                rebuild=lambda d: d["value"],
            )

        call()
        second = call()

        assert calls == [1]  # produce n'a tourné qu'une fois
        assert second.replayed is True
        assert second.result == "RESULT"

    def test_in_flight_key_without_result_raises_duplicate(self) -> None:
        guard, store = self._guard()
        # simule une opération concurrente : la clé est "remembered" mais pas encore résolue
        store.remember(KEY.scoped(user_id=str(USER_ID), route="POST /v1/transfers"), ttl_seconds=60)

        with pytest.raises(DuplicateOperation):
            guard.run(
                key=KEY,
                subject=str(USER_ID),
                route="POST /v1/transfers",
                produce=lambda: ("X", {"value": "X"}),
                rebuild=lambda d: d["value"],
            )

    def test_result_stored_by_a_concurrent_worker_is_replayed(self) -> None:
        """La 1re lecture ne trouve rien, ``remember`` échoue (course), la 2e lecture
        trouve le résultat qu'un worker concurrent vient d'écrire."""

        class RacingStore:
            def __init__(self) -> None:
                self._gets = 0

            def get_result(self, key: str) -> dict[str, str] | None:
                self._gets += 1
                return {"value": "FROM_PEER"} if self._gets >= 2 else None

            def remember(self, key: str, *, ttl_seconds: int) -> bool:
                return False

            def save_result(self, key: str, result: dict[str, str], *, ttl_seconds: int) -> None:
                raise AssertionError("ne doit pas écrire quand un pair a déjà résolu la clé")

            def forget(self, key: str) -> None:
                raise AssertionError("ne doit pas oublier la clé sur ce chemin")

        guard = IdempotencyGuard(RacingStore(), ttl_seconds=60)
        outcome = guard.run(
            key=KEY,
            subject=str(USER_ID),
            route="POST /v1/transfers",
            produce=lambda: ("LOCAL", {"value": "LOCAL"}),
            rebuild=lambda d: d["value"],
        )
        assert outcome.replayed is True
        assert outcome.result == "FROM_PEER"

    def test_failed_operation_releases_the_key_for_retry(self) -> None:
        guard, _ = self._guard()
        attempts = []

        def flaky() -> tuple[str, dict[str, str]]:
            attempts.append(1)
            if len(attempts) == 1:
                raise RuntimeError("panne transitoire")
            return "OK", {"value": "OK"}

        with pytest.raises(RuntimeError):
            guard.run(
                key=KEY,
                subject=str(USER_ID),
                route="POST /v1/transfers",
                produce=flaky,
                rebuild=lambda d: d["value"],
            )
        # même clé, nouvel essai : la clé a été libérée, l'opération repart
        retry = guard.run(
            key=KEY,
            subject=str(USER_ID),
            route="POST /v1/transfers",
            produce=flaky,
            rebuild=lambda d: d["value"],
        )
        assert retry.result == "OK"
        assert attempts == [1, 1]

    def test_keys_are_scoped_per_user_and_route(self) -> None:
        guard, _ = self._guard()
        r1 = guard.run(
            key=KEY,
            subject=str(USER_ID),
            route="POST /v1/transfers",
            produce=lambda: ("A", {"value": "A"}),
            rebuild=lambda d: d["value"],
        )
        r2 = guard.run(
            key=KEY,
            subject=str(EntityId(UUID(int=99))),
            route="POST /v1/transfers",
            produce=lambda: ("B", {"value": "B"}),
            rebuild=lambda d: d["value"],
        )
        assert (r1.result, r1.replayed) == ("A", False)
        assert (r2.result, r2.replayed) == ("B", False)
