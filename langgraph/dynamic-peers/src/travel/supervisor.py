"""A supervisor whose tools are generated from discovered workers."""

from __future__ import annotations

import logging
import os
import re
from typing import Awaitable, Callable

from langchain.agents import create_agent
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool, StructuredTool
from langchain_openai import ChatOpenAI

from travel.discovery import WorkerInfo

_logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gpt-4o-mini"

AskPeer = Callable[[str, str], Awaitable[str]]

_PROMPT_HEADER = (
    "You are a travel-planning supervisor. You cannot answer travel questions yourself; "
    "delegate to your workers with their tools, calling several when a request spans "
    "more than one. Finish with a short final answer. "
    "If no worker can handle part of a request, say so plainly."
)


def build_llm() -> BaseChatModel:
    return ChatOpenAI(model=os.getenv("OPENAI_MODEL", DEFAULT_MODEL), temperature=0)


def tool_name(worker_name: str) -> str:
    return "ask_" + re.sub(r"[^A-Za-z0-9_-]", "_", worker_name)


def describe(worker: WorkerInfo) -> str:
    skills = "; ".join(f"{n}: {d}" if d else n for n, d in worker.skills)
    parts = [worker.description or f"Worker {worker.name}"]
    if skills:
        parts.append(f"Skills: {skills}.")
    return " ".join(parts)


def build_prompt(workers: tuple[WorkerInfo, ...]) -> str:
    if not workers:
        return _PROMPT_HEADER + "\nYou currently have no workers, so you cannot help with requests."
    lines = [f"- {tool_name(w.name)}: {describe(w)}" for w in workers]
    return _PROMPT_HEADER + "\nYour workers:\n" + "\n".join(lines)


def peer_tools(workers: tuple[WorkerInfo, ...], ask_peer: AskPeer) -> list[BaseTool]:
    """One tool per worker; each delegates to that worker over A2A.

    A failing worker comes back to the model as an error string, so it can answer
    around it instead of the whole request failing.
    """

    def make(worker: WorkerInfo) -> BaseTool:
        async def delegate(request: str) -> str:
            try:
                return await ask_peer(worker.name, request)
            except Exception as e:
                _logger.exception("worker %r failed", worker.name)
                return f"Error: worker {worker.name!r} failed: {e}"

        return StructuredTool.from_function(
            coroutine=delegate,
            name=tool_name(worker.name),
            description=describe(worker),
        )

    return [make(w) for w in workers]


def build_supervisor(llm: BaseChatModel, workers: tuple[WorkerInfo, ...], ask_peer: AskPeer):
    return create_agent(
        llm,
        peer_tools(workers, ask_peer),
        system_prompt=build_prompt(workers),
    )
