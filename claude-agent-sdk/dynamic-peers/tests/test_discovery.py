import asyncio
import logging
import time
from unittest.mock import AsyncMock

import pytest
from a2a.types.a2a_pb2 import AgentCard, AgentSkill

from claude_travel.discovery import WorkerInfo, discover_workers

WARM = AsyncMock()


def card(description: str, *skills: tuple[str, str]) -> AgentCard:
    return AgentCard(
        description=description,
        skills=[AgentSkill(id=n, name=n, description=d) for n, d in skills],
    )


async def test_discovers_every_peer_sorted_by_name_with_card_details():
    cards = {"hotels": card("Finds hotels", ("search", "Hotel options")), "flights": card("Finds flights")}

    workers = await discover_workers(
        list_peers=lambda: ["hotels", "flights"],
        warm_client=WARM,
        resolve_card=AsyncMock(side_effect=lambda name: cards[name]),
    )

    assert workers == (
        WorkerInfo("flights", "Finds flights", ()),
        WorkerInfo("hotels", "Finds hotels", (("search", "Hotel options"),)),
    )


async def test_no_peers_yields_empty_tuple():
    resolve = AsyncMock()
    assert await discover_workers(list_peers=lambda: [], warm_client=WARM, resolve_card=resolve) == ()
    resolve.assert_not_awaited()


# A short budget and interval keep these fast; the logic is the same as the 60s default.
FAST = {"budget": 0.3, "interval": 0.01}


async def test_transient_failure_is_retried():
    resolve = AsyncMock(side_effect=[RuntimeError("not ready"), card("Finds flights")])

    workers = await discover_workers(list_peers=lambda: ["flights"], warm_client=WARM, resolve_card=resolve, **FAST)

    assert [w.name for w in workers] == ["flights"]
    assert resolve.await_count == 2


async def test_a_worker_that_starts_late_is_still_found():
    """The race: workers start with the supervisor, so one may take a while to come up."""
    start = time.monotonic()

    async def resolve(name):
        if name == "hotels" and time.monotonic() - start < 0.1:
            raise ConnectionError("connection refused")
        return card(f"{name} worker")

    workers = await discover_workers(
        list_peers=lambda: ["flights", "hotels"], warm_client=WARM, resolve_card=resolve, **FAST
    )

    assert [w.name for w in workers] == ["flights", "hotels"]


async def test_unreachable_peer_is_skipped_once_the_budget_is_spent():
    async def resolve(name):
        if name == "weather":
            raise RuntimeError("down")
        return card("ok")

    workers = await discover_workers(
        list_peers=lambda: ["weather", "flights"],
        warm_client=WARM,
        resolve_card=resolve,
        budget=0.05,
        interval=0.01,
    )

    assert [w.name for w in workers] == ["flights"]


async def test_peers_are_retried_concurrently_not_one_after_another():
    """Every peer's first attempt starts before any of them finishes."""
    started = 0
    all_started = asyncio.Event()

    async def resolve(name):
        nonlocal started
        started += 1
        if started == 3:
            all_started.set()
        await asyncio.wait_for(all_started.wait(), timeout=1)  # would hang if run in sequence
        return card(name)

    workers = await discover_workers(
        list_peers=lambda: ["a", "b", "c"], warm_client=WARM, resolve_card=resolve, **FAST
    )

    assert [w.name for w in workers] == ["a", "b", "c"]


async def test_returns_as_soon_as_every_peer_is_found():
    start = time.monotonic()

    await discover_workers(
        list_peers=lambda: ["a", "b"],
        warm_client=WARM,
        resolve_card=AsyncMock(return_value=card("ok")),
        budget=30,
        interval=10,
    )

    assert time.monotonic() - start < 1  # no sleeping when nothing is missing


async def test_a_hung_attempt_cannot_outlast_the_budget():
    async def resolve(name):
        await asyncio.sleep(30)

    start = time.monotonic()
    workers = await discover_workers(
        list_peers=lambda: ["weather"], warm_client=WARM, resolve_card=resolve, budget=0.1, interval=0.01
    )

    assert workers == ()
    assert time.monotonic() - start < 2


async def test_failed_attempts_log_one_line_and_only_the_final_failure_a_traceback(caplog):
    caplog.set_level(logging.WARNING)

    await discover_workers(
        list_peers=lambda: ["weather"],
        warm_client=WARM,
        resolve_card=AsyncMock(side_effect=ConnectionError("connection refused")),
        budget=0.1,
        interval=0.02,
    )

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(warnings) >= 2
    assert all(r.exc_info is None for r in warnings)
    assert "ConnectionError: connection refused" in warnings[0].getMessage()
    assert len(errors) == 1 and errors[0].exc_info is not None


async def test_no_peers_means_no_waiting():
    start = time.monotonic()
    assert await discover_workers(list_peers=lambda: [], warm_client=WARM, resolve_card=AsyncMock()) == ()
    assert time.monotonic() - start < 0.5


async def test_topology_errors_propagate():
    def boom():
        raise LookupError("no topology")

    with pytest.raises(LookupError):
        await discover_workers(list_peers=boom, warm_client=WARM, resolve_card=AsyncMock())


async def test_every_peer_is_warmed_so_drift_detection_knows_its_card():
    warm = AsyncMock()

    await discover_workers(
        list_peers=lambda: ["hotels", "flights"],
        warm_client=warm,
        resolve_card=AsyncMock(return_value=card("ok")),
        **FAST,
    )

    assert sorted(c.args[0] for c in warm.await_args_list) == ["flights", "hotels"]


async def test_peer_that_cannot_be_warmed_is_skipped():
    warm = AsyncMock(side_effect=RuntimeError("unreachable"))
    resolve = AsyncMock()

    workers = await discover_workers(
        list_peers=lambda: ["weather"], warm_client=warm, resolve_card=resolve, budget=0.05, interval=0.01
    )

    assert workers == ()
    resolve.assert_not_awaited()
