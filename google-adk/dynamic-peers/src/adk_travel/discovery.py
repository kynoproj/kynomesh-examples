"""Discover the supervisor's workers from the Kynomesh topology and their AgentCards.

Nothing here names a worker: it asks Kynomesh who the peers are, then asks each
peer who it is. The peer list and cached cards are fixed for the life of the
process, so a changed AgentSet takes effect when Kynomesh restarts the pod (on a
topology change, or on AgentCard drift when `driftReload` is enabled).

All agents in an AgentSet start at the same time, so a worker is often not up yet
when the supervisor starts looking for it. Discovery therefore retries every peer
at once, for up to `STARTUP_BUDGET` seconds, and returns as soon as every peer has
answered. The budget has to stay well under the pod's startup-probe window: until
discovery returns, the supervisor is not serving and the pod is not yet ready.

Each peer is also warmed with `client.peer_client`. That records the peer's card
hash, which is what `driftReload` compares against: a peer this process never built
a client for is "unknown" to drift detection, not "drifted". The a2a `Client` does
not expose its card, so the card itself comes from `resolve_agent_card`.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Awaitable, Callable

from a2a.types.a2a_pb2 import AgentCard
from kynomesh import client

_logger = logging.getLogger(__name__)

# The agent container's startup probe allows roughly 150s (estimated: 5s period, 30
# failures), and nothing is served until discovery returns. Stay well under that.
STARTUP_BUDGET = 60.0  # seconds to wait for every peer, in total
RETRY_INTERVAL = 2.0  # seconds between attempts at one peer


@dataclass(frozen=True)
class WorkerInfo:
    name: str
    description: str
    skills: tuple[tuple[str, str], ...]  # (name, description)


def worker_from_card(name: str, card: AgentCard) -> WorkerInfo:
    return WorkerInfo(
        name=name,
        description=card.description,
        skills=tuple((s.name, s.description) for s in card.skills),
    )


async def discover_workers(
    *,
    list_peers: Callable[[], list[str]] = client.peers,
    resolve_card: Callable[[str], Awaitable[AgentCard]] = client.resolve_agent_card,
    warm_client: Callable[[str], Awaitable[object]] = client.peer_client,
    budget: float = STARTUP_BUDGET,
    interval: float = RETRY_INTERVAL,
) -> tuple[WorkerInfo, ...]:
    """Return every reachable peer as a WorkerInfo, sorted by name.

    Peers are retried concurrently until each answers or `budget` seconds pass, so
    the wait is the slowest worker's start time, not the sum of all of them, and
    it is zero extra when every worker is already up. A peer that is still
    unreachable when the budget runs out is logged and skipped, so one dead worker
    cannot keep the supervisor from starting.
    """
    deadline = asyncio.get_running_loop().time() + budget
    names = sorted(list_peers())
    cards = await asyncio.gather(
        *(_resolve_until(name, warm_client, resolve_card, deadline, interval) for name in names)
    )
    return tuple(worker_from_card(n, c) for n, c in zip(names, cards) if c is not None)


async def _resolve_until(name, warm_client, resolve_card, deadline: float, interval: float):
    """Try to reach `name` until `deadline`; return its card, or None if it never answered."""
    loop = asyncio.get_running_loop()

    async def attempt() -> AgentCard:
        await warm_client(name)
        return await resolve_card(name)

    attempts = 0
    while True:
        attempts += 1
        try:
            # Bound the attempt too: a hung connection must not outlast the budget.
            return await asyncio.wait_for(attempt(), timeout=max(deadline - loop.time(), 0.001))
        except Exception as e:
            if deadline - loop.time() <= interval:
                _logger.error(
                    "skipping peer %r: still unreachable after %d attempts", name, attempts, exc_info=True
                )
                return None
            # One line per attempt; the traceback is saved for the final failure.
            _logger.warning(
                "peer %r not reachable yet (attempt %d): %s: %s", name, attempts, type(e).__name__, e
            )
            await asyncio.sleep(interval)
