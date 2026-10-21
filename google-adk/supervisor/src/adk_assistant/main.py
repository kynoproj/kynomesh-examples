"""Serve one role (assistant, researcher or calculator) over A2A via Kynomesh.

One image runs all three agents; the AgentSet picks the role with --role.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal

from google.adk.runners import Runner
from kynomesh import server

from adk_assistant import agents
from adk_assistant.agents import run_agent
from adk_assistant.cards import ROLES, agent_card
from adk_assistant.executor import AdkExecutor
from adk_assistant.peers import ask_peer

logging.basicConfig(level=logging.INFO)


def build_runner(role: str) -> Runner:
    if role == "assistant":
        return agents.build_supervisor(ask_peer)
    if role == "researcher":
        return agents.build_researcher()
    if role == "calculator":
        return agents.build_calculator()
    raise ValueError(f"unknown role {role!r}")


async def serve(role: str) -> None:
    runner = build_runner(role)

    async def run(prompt: str) -> str:
        return await run_agent(prompt, runner=runner)

    loop = asyncio.get_running_loop()
    serve_task = asyncio.ensure_future(server.start(AdkExecutor(run), agent_card(role)))
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, serve_task.cancel)
    try:
        await serve_task
    except asyncio.CancelledError:
        pass


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--role", required=True, choices=ROLES)
    args = parser.parse_args()
    if not os.getenv("GOOGLE_API_KEY"):
        raise SystemExit("GOOGLE_API_KEY must be set (see README)")
    asyncio.run(serve(args.role))


if __name__ == "__main__":
    main()
