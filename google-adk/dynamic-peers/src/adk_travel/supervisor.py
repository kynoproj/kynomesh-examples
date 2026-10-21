"""A supervisor whose tools are generated from discovered workers."""

from __future__ import annotations

import logging
import re
from typing import Awaitable, Callable

from google.adk.runners import Runner

from adk_travel.agent import build_runner
from adk_travel.discovery import WorkerInfo
from adk_travel.tools import failed, ok

_logger = logging.getLogger(__name__)

AskPeer = Callable[[str, str], Awaitable[str]]

_INSTRUCTION_HEADER = (
    "You are a travel-planning supervisor. You cannot answer travel questions yourself; "
    "delegate to your workers with their tools, calling several when a request spans "
    "more than one. Finish with a short final answer. "
    "If no worker can handle part of a request, say so plainly."
)


def tool_name(worker_name: str) -> str:
    return "ask_" + re.sub(r"[^A-Za-z0-9_]", "_", worker_name)


def describe(worker: WorkerInfo) -> str:
    skills = "; ".join(f"{n}: {d}" if d else n for n, d in worker.skills)
    parts = [worker.description or f"Worker {worker.name}"]
    if skills:
        parts.append(f"Skills: {skills}.")
    return " ".join(parts)


def build_instruction(workers: tuple[WorkerInfo, ...]) -> str:
    if not workers:
        return _INSTRUCTION_HEADER + "\nYou currently have no workers, so you cannot help with requests."
    lines = [f"- {tool_name(w.name)}: {describe(w)}" for w in workers]
    return _INSTRUCTION_HEADER + "\nYour workers:\n" + "\n".join(lines)


def peer_tools(workers: tuple[WorkerInfo, ...], ask_peer: AskPeer) -> list[Callable]:
    """One tool function per worker; each delegates to that worker over A2A.

    ADK reads a tool's name from `__name__` and its description from the
    docstring, so both are set from the worker's card. The argument's schema
    comes from the type hint.
    """

    def make(worker: WorkerInfo) -> Callable:
        async def delegate(request: str) -> dict[str, str]:
            try:
                return ok(await ask_peer(worker.name, request))
            except Exception as e:  # the model should see a failed worker, not crash the run
                _logger.exception("worker %r failed", worker.name)
                return failed(f"worker {worker.name!r} failed: {e}")

        delegate.__name__ = tool_name(worker.name)
        delegate.__doc__ = f"{describe(worker)} Pass `request` as a plain-language ask."
        return delegate

    return [make(w) for w in workers]


def build_supervisor_runner(workers: tuple[WorkerInfo, ...], ask_peer: AskPeer) -> Runner:
    return build_runner(
        name="planner",
        instruction=build_instruction(workers),
        tools=peer_tools(workers, ask_peer),
    )
