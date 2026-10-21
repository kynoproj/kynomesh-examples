"""The three LangGraph agents."""

from __future__ import annotations

import logging
import os
from typing import Awaitable, Callable

from langchain.agents import create_agent
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool, tool
from langchain_openai import ChatOpenAI

from assistant.tools import CALCULATOR_TOOLS, RESEARCHER_TOOLS

_logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gpt-4o-mini"

RESEARCHER_PROMPT = (
    "You are a research expert. Use the lookup_fact tool to answer factual questions. "
    "Reply with the facts only; do not do arithmetic."
)
CALCULATOR_PROMPT = (
    "You are a math expert. Use the arithmetic tools for every calculation. "
    "Reply with the numeric result only; do not look up facts."
)
SUPERVISOR_PROMPT = (
    "You are a supervisor with two workers: the researcher (facts) and the calculator "
    "(arithmetic). Delegate with the ask_researcher and ask_calculator tools; call both, "
    "one after the other, when a question needs both. Never answer facts or math yourself. "
    "Finish with a short final answer."
)

AskPeer = Callable[[str, str], Awaitable[str]]


def build_llm() -> BaseChatModel:
    return ChatOpenAI(model=os.getenv("OPENAI_MODEL", DEFAULT_MODEL), temperature=0)


def build_researcher(llm: BaseChatModel):
    return create_agent(llm, RESEARCHER_TOOLS, system_prompt=RESEARCHER_PROMPT)


def build_calculator(llm: BaseChatModel):
    return create_agent(llm, CALCULATOR_TOOLS, system_prompt=CALCULATOR_PROMPT)


def peer_tools(ask_peer: AskPeer) -> list[BaseTool]:
    """Tools that delegate to the worker agents over A2A.

    A failing worker (for example one that is still starting) comes back to the
    model as an error string, so it can answer around it instead of the whole
    request failing.
    """

    async def delegate(worker: str, request: str) -> str:
        try:
            return await ask_peer(worker, request)
        except Exception as e:
            _logger.exception("worker %r failed", worker)
            return f"Error: worker {worker!r} failed: {e}"

    @tool
    async def ask_researcher(question: str) -> str:
        """Ask the researcher worker a factual question."""
        return await delegate("researcher", question)

    @tool
    async def ask_calculator(problem: str) -> str:
        """Ask the calculator worker to solve an arithmetic problem."""
        return await delegate("calculator", problem)

    return [ask_researcher, ask_calculator]


def build_supervisor(llm: BaseChatModel, ask_peer: AskPeer):
    return create_agent(llm, peer_tools(ask_peer), system_prompt=SUPERVISOR_PROMPT)
