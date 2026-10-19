"""Discover the supervisor's workers from the Kynomesh topology and their AgentCards.

Nothing here names a worker: it asks Kynomesh who the peers are, then asks each
peer who it is. The peer list and cached cards are fixed for the life of the
process, so a changed AgentSet takes effect when Kynomesh restarts the pod (on a
topology change, or on AgentCard drift when `driftReload` is enabled).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Awaitable, Callable

from a2a.types.a2a_pb2 import AgentCard
from kynomesh import client

_logger = logging.getLogger(__name__)


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
    attempts: int = 3,
    delay: float = 2.0,
) -> tuple[WorkerInfo, ...]:
    """Return every reachable peer as a WorkerInfo, sorted by name.

    A peer that cannot be reached after `attempts` tries is logged and skipped,
    so one slow worker does not keep the supervisor from starting.
    """
    workers: list[WorkerInfo] = []
    for name in sorted(list_peers()):
        card = await _resolve_with_retry(name, warm_client, resolve_card, attempts, delay)
        if card is not None:
            workers.append(worker_from_card(name, card))
    return tuple(workers)


async def _resolve_with_retry(name, warm_client, resolve_card, attempts: int, delay: float):
    for attempt in range(1, attempts + 1):
        try:
            await warm_client(name)
            return await resolve_card(name)
        except Exception:
            _logger.warning("reaching peer %r failed (%d/%d)", name, attempt, attempts, exc_info=True)
            if attempt < attempts:
                await asyncio.sleep(delay)
    _logger.error("skipping peer %r: unreachable", name)
    return None
