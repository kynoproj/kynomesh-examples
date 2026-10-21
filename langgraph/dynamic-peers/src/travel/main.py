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
from langchain.agents import create_agent
from kynomesh import client, server

from travel import supervisor as supervisor_module
from travel.cards import supervisor_card, worker_card
from travel.discovery import discover_workers
from travel.executor import LangGraphExecutor
from travel.peers import ask_peer
from travel.workers import EXTRA_SKILLS_ENV, WORKERS, with_extra_skills

logging.basicConfig(level=logging.INFO)
_logger = logging.getLogger("travel")

ENTRY_ROLE = "planner"


async def build_supervisor_agent() -> tuple[object, AgentCard]:
    workers = await discover_workers()
    _logger.info("discovered workers: %s", [w.name for w in workers])
    graph = supervisor_module.build_supervisor(supervisor_module.build_llm(), workers, ask_peer)
    return graph, supervisor_card()


def build_worker_agent(role: str) -> tuple[object, AgentCard]:
    spec = WORKERS[role]
    prompt = with_extra_skills(spec.prompt, os.getenv(EXTRA_SKILLS_ENV, ""))
    graph = create_agent(supervisor_module.build_llm(), list(spec.tools), system_prompt=prompt)
    return graph, worker_card(role)


async def serve(role: str) -> None:
    if role == ENTRY_ROLE:
        graph, card = await build_supervisor_agent()
    else:
        graph, card = build_worker_agent(role)

    loop = asyncio.get_running_loop()
    serve_task = asyncio.ensure_future(server.start(LangGraphExecutor(graph), card))
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
