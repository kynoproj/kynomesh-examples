"""The three CrewAI agents, each served from its own pod.

A standalone `Agent` answers each request with `kickoff_async`, starting from a
clean conversation, so there is no Task or Crew to wire up.
"""

from __future__ import annotations

import logging
import os
from typing import Callable

from crewai import LLM, Agent
from crewai.tools import BaseTool, tool
from crewai_core.printer import set_suppress_console_output

from crew_assistant.tools import CALCULATOR_TOOLS, RESEARCHER_TOOLS

_logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gpt-4o-mini"
MAX_ITER = 8

AskPeer = Callable[[str, str], str]  # blocking: (worker name, request) -> reply


class AgentError(RuntimeError):
    """The CrewAI run ended without a usable reply."""


def build_llm() -> LLM:
    return LLM(model=os.getenv("OPENAI_MODEL") or DEFAULT_MODEL, temperature=0)


def _agent(llm: LLM | None, *, role: str, goal: str, backstory: str, tools: list[BaseTool]) -> Agent:
    return Agent(
        role=role,
        goal=goal,
        backstory=backstory,
        llm=llm or build_llm(),
        tools=tools,
        max_iter=MAX_ITER,  # bounds the tool-use loop
        verbose=False,
    )


def build_researcher(llm: LLM | None = None) -> Agent:
    return _agent(
        llm,
        role="Research expert",
        goal="Answer factual questions",
        backstory=(
            "Use the lookup_fact tool to answer factual questions. "
            "Reply with the facts only; do not do arithmetic."
        ),
        tools=RESEARCHER_TOOLS,
    )


def build_calculator(llm: LLM | None = None) -> Agent:
    return _agent(
        llm,
        role="Math expert",
        goal="Solve arithmetic problems",
        backstory=(
            "Use the arithmetic tools for every calculation. "
            "Reply with the numeric result only; do not look up facts."
        ),
        tools=CALCULATOR_TOOLS,
    )


def peer_tools(ask_peer: AskPeer) -> list[BaseTool]:
    """Tools that delegate to the worker agents over A2A.

    A failing worker comes back to the model as an error string, so it can answer
    around it instead of the whole run crashing.
    """

    def delegate(worker: str, request: str) -> str:
        try:
            return ask_peer(worker, request)
        except Exception as e:
            _logger.exception("worker %r failed", worker)
            return f"Error: worker {worker!r} failed: {e}"

    @tool("ask_researcher")
    def ask_researcher(question: str) -> str:
        """Ask the researcher worker a factual question."""
        return delegate("researcher", question)

    @tool("ask_calculator")
    def ask_calculator(problem: str) -> str:
        """Ask the calculator worker to solve an arithmetic problem."""
        return delegate("calculator", problem)

    return [ask_researcher, ask_calculator]


def build_supervisor(ask_peer: AskPeer, llm: LLM | None = None) -> Agent:
    return _agent(
        llm,
        role="Assistant",
        goal="Answer questions by delegating to your workers",
        backstory=(
            "You have two workers: the researcher (facts) and the calculator (arithmetic). "
            "Delegate with the ask_researcher and ask_calculator tools; call both, one after "
            "the other, when a question needs both. Never answer facts or math yourself. "
            "Finish with a short final answer."
        ),
        tools=peer_tools(ask_peer),
    )


async def run_agent(prompt: str, *, agent: Agent) -> str:
    """Run the agent on `prompt` and return its final text."""
    set_suppress_console_output(True)  # CrewAI draws panels to stdout; keep pod logs clean
    output = await agent.kickoff_async(prompt)
    if not output.raw:
        raise AgentError("CrewAI finished without a final answer")
    return output.raw
