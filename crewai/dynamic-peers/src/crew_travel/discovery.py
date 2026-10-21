"""Discover the supervisor's workers from the Kynomesh topology and their AgentCards.

Nothing here names a worker: it asks Kynomesh who the peers are, then asks each
peer who it is. The peer list and cached cards are fixed for the life of the
process, so a changed AgentSet takes effect when Kynomesh restarts the pod (on a
topology change, or on AgentCard drift when `driftReload` is enabled).

Every agent in an AgentSet starts at the same time, so a worker may not be up yet
when the supervisor looks for it. Each peer is retried for about a minute. If one
is still unreachable, discovery raises: the container exits and Kubernetes
restarts the pod, which tries again. The wait stays inside the container's startup
window, because the supervisor does not serve until discovery returns.

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

ATTEMPTS = 12  # tries per peer
DELAY = 5.0  # seconds between tries, so a peer gets about a minute


class PeerUnreachableError(RuntimeError):
    """A peer could not be reached within the retry budget."""


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
    attempts: int = ATTEMPTS,
    delay: float = DELAY,
) -> tuple[WorkerInfo, ...]:
    """Return every peer as a WorkerInfo, sorted by name.

    Raises PeerUnreachableError if a peer still cannot be reached after
    `attempts` tries, so the pod restarts instead of serving without that worker.
    """
    workers: list[WorkerInfo] = []
    for name in sorted(list_peers()):
        card = await _resolve_with_retry(name, warm_client, resolve_card, attempts, delay)
        workers.append(worker_from_card(name, card))
    return tuple(workers)


async def _resolve_with_retry(name, warm_client, resolve_card, attempts: int, delay: float) -> AgentCard:
    for attempt in range(1, attempts + 1):
        try:
            await warm_client(name)
            return await resolve_card(name)
        except Exception as e:
            if attempt == attempts:
                raise PeerUnreachableError(f"peer {name!r} unreachable after {attempts} attempts") from e
            _logger.warning(
                "peer %r not reachable yet (%d/%d): %s: %s", name, attempt, attempts, type(e).__name__, e
            )
            await asyncio.sleep(delay)
    raise AssertionError("unreachable")  # attempts < 1
