"""Serve one role (assistant, researcher or calculator) over A2A via Kynomesh.

One image runs all three agents; the AgentSet picks the role with --role.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal

from crewai import Agent
from kynomesh import server

from crew_assistant import agents
from crew_assistant.agents import run_agent
from crew_assistant.cards import ROLES, agent_card
from crew_assistant.executor import CrewExecutor
from crew_assistant.peers import ask_peer, blocking_ask

logging.basicConfig(level=logging.INFO)


def build_agent(role: str, loop: asyncio.AbstractEventLoop) -> Agent:
    if role == "assistant":
        return agents.build_supervisor(blocking_ask(ask_peer, loop))
    if role == "researcher":
        return agents.build_researcher()
    if role == "calculator":
        return agents.build_calculator()
    raise ValueError(f"unknown role {role!r}")


async def serve(role: str) -> None:
    loop = asyncio.get_running_loop()
    agent = build_agent(role, loop)

    async def run(prompt: str) -> str:
        return await run_agent(prompt, agent=agent)

    serve_task = asyncio.ensure_future(server.start(CrewExecutor(run), agent_card(role)))
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
    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY must be set (see README)")
    asyncio.run(serve(args.role))


if __name__ == "__main__":
    main()
