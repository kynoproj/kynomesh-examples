"""Serve the planner or one worker role over A2A via Kynomesh.

One image runs every agent; the AgentSet picks the role with --role. Workers are
whatever roles the manifest deploys. The planner is the same in every case: it
discovers its workers at startup.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal

from a2a.types.a2a_pb2 import AgentCard
from kynomesh import client, server

from crew_travel.agent import build_agent, run_agent
from crew_travel.cards import supervisor_card, worker_card
from crew_travel.discovery import discover_workers
from crew_travel.executor import CrewExecutor, Run
from crew_travel.peers import ask_peer, blocking_ask
from crew_travel.supervisor import build_supervisor
from crew_travel.workers import WORKERS

logging.basicConfig(level=logging.INFO)
_logger = logging.getLogger("crew_travel")

ENTRY_ROLE = "planner"


async def build_supervisor_agent() -> tuple[Run, AgentCard]:
    workers = await discover_workers()
    _logger.info("discovered workers: %s", [w.name for w in workers])
    agent = build_supervisor(workers, blocking_ask(ask_peer, asyncio.get_running_loop()))

    async def run(prompt: str) -> str:
        return await run_agent(prompt, agent=agent)

    return run, supervisor_card()


def build_worker_agent(role: str) -> tuple[Run, AgentCard]:
    spec = WORKERS[role]
    agent = build_agent(role=role, instruction=spec.instruction, tools=spec.tools)

    async def run(prompt: str) -> str:
        return await run_agent(prompt, agent=agent)

    return run, worker_card(role)


async def serve(role: str) -> None:
    if role == ENTRY_ROLE:
        run, card = await build_supervisor_agent()
    else:
        run, card = build_worker_agent(role)

    loop = asyncio.get_running_loop()
    serve_task = asyncio.ensure_future(server.start(CrewExecutor(run), card))
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, serve_task.cancel)
    try:
        await serve_task
    except asyncio.CancelledError:
        pass


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--role", required=True, choices=[ENTRY_ROLE, *WORKERS])
    args = parser.parse_args()
    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY must be set (see README)")
    try:
        asyncio.run(serve(args.role))
    except client.TopologyNotAvailableError:
        raise SystemExit(
            "no Kynomesh topology found: the planner only runs inside an AgentSet "
            "(workers can run locally)"
        ) from None


if __name__ == "__main__":
    main()
