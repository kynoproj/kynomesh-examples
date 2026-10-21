"""The three ADK agents, each served from its own pod.

Every role is an `LlmAgent` whose only capabilities are its own tools, run in a
fresh in-memory session per request so requests are independent.
"""

from __future__ import annotations

import os
import uuid
from typing import Awaitable, Callable, Sequence

from google.adk.agents import LlmAgent
from google.adk.runners import InMemoryRunner, Runner
from google.genai import types

from adk_assistant.tools import CALCULATOR_TOOLS, RESEARCHER_TOOLS, failed, ok

APP_NAME = "adk-supervisor"
USER_ID = "a2a"
DEFAULT_MODEL = "gemini-2.5-flash"

RESEARCHER_INSTRUCTION = (
    "You are a research expert. Use the lookup_fact tool to answer factual questions. "
    "Reply with the facts only; do not do arithmetic."
)
CALCULATOR_INSTRUCTION = (
    "You are a math expert. Use the arithmetic tools for every calculation. "
    "Reply with the numeric result only; do not look up facts."
)
SUPERVISOR_INSTRUCTION = (
    "You are a supervisor with two workers: the researcher (facts) and the calculator "
    "(arithmetic). Delegate with the ask_researcher and ask_calculator tools; call both, "
    "one after the other, when a question needs both. Never answer facts or math yourself. "
    "Finish with a short final answer."
)

AskPeer = Callable[[str, str], Awaitable[str]]


class AgentError(RuntimeError):
    """The ADK run ended without a usable reply."""


def build_runner(*, name: str, instruction: str, tools: Sequence[Callable]) -> Runner:
    agent = LlmAgent(
        name=name,
        model=os.getenv("GOOGLE_MODEL") or DEFAULT_MODEL,
        instruction=instruction,
        tools=list(tools),
    )
    return InMemoryRunner(agent=agent, app_name=APP_NAME)


def build_researcher() -> Runner:
    return build_runner(name="researcher", instruction=RESEARCHER_INSTRUCTION, tools=RESEARCHER_TOOLS)


def build_calculator() -> Runner:
    return build_runner(name="calculator", instruction=CALCULATOR_INSTRUCTION, tools=CALCULATOR_TOOLS)


def peer_tools(ask_peer: AskPeer) -> list[Callable]:
    """Tools that delegate to the worker agents over A2A.

    A failing worker comes back to the model as an error result, so it can answer
    around it instead of the whole run crashing.
    """

    async def delegate(worker: str, request: str) -> dict:
        try:
            return ok(await ask_peer(worker, request))
        except Exception as e:
            return failed(f"worker {worker!r} failed: {e}")

    async def ask_researcher(question: str) -> dict:
        """Ask the researcher worker a factual question.

        Args:
            question: The factual question to answer.
        """
        return await delegate("researcher", question)

    async def ask_calculator(problem: str) -> dict:
        """Ask the calculator worker to solve an arithmetic problem.

        Args:
            problem: The arithmetic problem, in plain language.
        """
        return await delegate("calculator", problem)

    return [ask_researcher, ask_calculator]


def build_supervisor(ask_peer: AskPeer) -> Runner:
    return build_runner(name="assistant", instruction=SUPERVISOR_INSTRUCTION, tools=peer_tools(ask_peer))


async def run_agent(prompt: str, *, runner: Runner) -> str:
    """Run the agent on `prompt` in a fresh session and return its final text."""
    session = await runner.session_service.create_session(
        app_name=APP_NAME, user_id=USER_ID, session_id=str(uuid.uuid4())
    )
    message = types.Content(role="user", parts=[types.Part(text=prompt)])
    reply = ""
    async for event in runner.run_async(user_id=USER_ID, session_id=session.id, new_message=message):
        if event.error_code or event.error_message:
            raise AgentError(f"ADK run failed: {event.error_code} {event.error_message or ''}".strip())
        if event.is_final_response() and event.content and event.content.parts:
            reply = "".join(part.text or "" for part in event.content.parts)
    if not reply:
        raise AgentError("ADK finished without a final response")
    return reply
