import asyncio
import sys

import pytest

from crew_assistant import main


@pytest.mark.parametrize(
    ("role", "tools"),
    [
        ("assistant", ["ask_researcher", "ask_calculator"]),
        ("researcher", ["lookup_fact"]),
        ("calculator", ["add", "multiply", "divide"]),
    ],
)
async def test_agent_per_role(role, tools):
    agent = main.build_agent(role, asyncio.get_running_loop())
    assert [t.name for t in agent.tools] == tools


async def test_unknown_role_rejected_by_build_agent():
    with pytest.raises(ValueError):
        main.build_agent("planner", asyncio.get_running_loop())


def test_missing_api_key_exits_with_message(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(sys, "argv", ["x", "--role", "calculator"])
    with pytest.raises(SystemExit, match="OPENAI_API_KEY"):
        main.main()


def test_unknown_role_rejected_on_the_command_line(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["x", "--role", "pilot"])
    with pytest.raises(SystemExit):
        main.main()


def test_main_serves_the_requested_role(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.setattr(sys, "argv", ["x", "--role", "researcher"])
    served = []

    async def fake_serve(role):
        served.append(role)

    monkeypatch.setattr(main, "serve", fake_serve)
    main.main()

    assert served == ["researcher"]
