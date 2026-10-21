"""Serve one role (assistant, researcher or calculator) over A2A via Kynomesh.

One image runs all three agents; the AgentSet picks the role with --role.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal

from kynomesh import server

from assistant import agents
from assistant.cards import ROLES, agent_card
from assistant.executor import LangGraphExecutor
from assistant.peers import ask_peer

logging.basicConfig(level=logging.INFO)


def build_graph(role: str):
    llm = agents.build_llm()
    if role == "assistant":
        return agents.build_supervisor(llm, ask_peer)
    if role == "researcher":
        return agents.build_researcher(llm)
    if role == "calculator":
        return agents.build_calculator(llm)
    raise ValueError(f"unknown role {role!r}")


async def serve(role: str) -> None:
    loop = asyncio.get_running_loop()
    serve_task = asyncio.ensure_future(
        server.start(LangGraphExecutor(build_graph(role)), agent_card(role))
    )
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
