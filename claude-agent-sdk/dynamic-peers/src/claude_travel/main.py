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

from claude_travel.agent import locked_down_options, run_agent
from claude_travel.cards import supervisor_card, worker_card
from claude_travel.discovery import discover_workers
from claude_travel.executor import ClaudeExecutor, Run
from claude_travel.peers import ask_peer
from claude_travel.supervisor import supervisor_options
from claude_travel.workers import EXTRA_SKILLS_ENV, WORKERS, with_extra_skills

logging.basicConfig(level=logging.INFO)
_logger = logging.getLogger("claude_travel")

ENTRY_ROLE = "planner"


async def build_supervisor_agent() -> tuple[Run, AgentCard]:
    workers = await discover_workers()
    _logger.info("discovered workers: %s", [w.name for w in workers])

    async def run(prompt: str) -> str:
        return await run_agent(prompt, options=supervisor_options(workers, ask_peer))

    return run, supervisor_card()


def build_worker_agent(role: str) -> tuple[Run, AgentCard]:
    spec = WORKERS[role]
    system_prompt = with_extra_skills(spec.prompt, os.getenv(EXTRA_SKILLS_ENV, ""))

    async def run(prompt: str) -> str:
        options = locked_down_options(system_prompt=system_prompt, tools=spec.tools)
        return await run_agent(prompt, options=options)

    return run, worker_card(role)


async def serve(role: str) -> None:
    if role == ENTRY_ROLE:
        run, card = await build_supervisor_agent()
    else:
        run, card = build_worker_agent(role)

    loop = asyncio.get_running_loop()
    serve_task = asyncio.ensure_future(server.start(ClaudeExecutor(run), card))
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
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise SystemExit("ANTHROPIC_API_KEY must be set (see README)")
    try:
        asyncio.run(serve(args.role))
    except client.TopologyNotAvailableError:
        raise SystemExit(
            "no Kynomesh topology found: the planner only runs inside an AgentSet "
            "(workers can run locally)"
        ) from None


if __name__ == "__main__":
    main()
