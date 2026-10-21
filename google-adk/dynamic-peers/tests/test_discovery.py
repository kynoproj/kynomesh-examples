import logging
from unittest.mock import AsyncMock

import pytest
from a2a.types.a2a_pb2 import AgentCard, AgentSkill

from adk_travel.discovery import PeerUnreachableError, WorkerInfo, discover_workers

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


async def test_transient_failure_is_retried():
    resolve = AsyncMock(side_effect=[RuntimeError("not ready"), card("Finds flights")])

    workers = await discover_workers(list_peers=lambda: ["flights"], warm_client=WARM, resolve_card=resolve, delay=0)

    assert [w.name for w in workers] == ["flights"]
    assert resolve.await_count == 2


async def test_a_worker_that_starts_late_is_still_found():
    """The race: workers start with the supervisor, so one may take a while to come up."""
    failures = {"hotels": 4}

    async def resolve(name):
        if failures.get(name, 0) > 0:
            failures[name] -= 1
            raise ConnectionError("connection refused")
        return card(f"{name} worker")

    workers = await discover_workers(
        list_peers=lambda: ["flights", "hotels"], warm_client=WARM, resolve_card=resolve, attempts=6, delay=0
    )

    assert [w.name for w in workers] == ["flights", "hotels"]


async def test_unreachable_peer_raises_so_the_pod_restarts():
    resolve = AsyncMock(side_effect=ConnectionError("connection refused"))

    with pytest.raises(PeerUnreachableError, match="'weather' unreachable after 3 attempts") as info:
        await discover_workers(
            list_peers=lambda: ["weather"], warm_client=WARM, resolve_card=resolve, attempts=3, delay=0
        )

    assert isinstance(info.value.__cause__, ConnectionError)  # the real reason is kept
    assert resolve.await_count == 3


async def test_failed_attempts_log_one_line_each_without_a_traceback(caplog):
    caplog.set_level(logging.WARNING)

    with pytest.raises(PeerUnreachableError):
        await discover_workers(
            list_peers=lambda: ["weather"],
            warm_client=WARM,
            resolve_card=AsyncMock(side_effect=ConnectionError("connection refused")),
            attempts=3,
            delay=0,
        )

    assert len(caplog.records) == 2  # the last failure is raised, not logged
    assert all(r.exc_info is None for r in caplog.records)
    assert "ConnectionError: connection refused" in caplog.records[0].getMessage()


async def test_retry_budget_is_about_a_minute_per_peer():
    from adk_travel import discovery

    assert 45 <= (discovery.ATTEMPTS - 1) * discovery.DELAY <= 90


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
    )

    assert [c.args[0] for c in warm.await_args_list] == ["flights", "hotels"]


async def test_peer_that_cannot_be_warmed_raises_without_resolving_its_card():
    warm = AsyncMock(side_effect=RuntimeError("unreachable"))
    resolve = AsyncMock()

    with pytest.raises(PeerUnreachableError):
        await discover_workers(
            list_peers=lambda: ["weather"], warm_client=warm, resolve_card=resolve, attempts=2, delay=0
        )

    resolve.assert_not_awaited()
