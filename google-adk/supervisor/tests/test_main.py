import sys

import pytest

from adk_assistant import main


@pytest.mark.parametrize(
    ("role", "tools"),
    [
        ("assistant", ["ask_researcher", "ask_calculator"]),
        ("researcher", ["lookup_fact"]),
        ("calculator", ["add", "multiply", "divide"]),
    ],
)
def test_runner_per_role(role, tools):
    assert [t.__name__ for t in main.build_runner(role).agent.tools] == tools


def test_unknown_role_rejected_by_build_runner():
    with pytest.raises(ValueError):
        main.build_runner("planner")


def test_missing_api_key_exits_with_message(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setattr(sys, "argv", ["x", "--role", "calculator"])
    with pytest.raises(SystemExit, match="GOOGLE_API_KEY"):
        main.main()


def test_unknown_role_rejected_on_the_command_line(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["x", "--role", "pilot"])
    with pytest.raises(SystemExit):
        main.main()


def test_main_serves_the_requested_role(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "x")
    monkeypatch.setattr(sys, "argv", ["x", "--role", "researcher"])
    served = []

    async def fake_serve(role):
        served.append(role)

    monkeypatch.setattr(main, "serve", fake_serve)
    main.main()

    assert served == ["researcher"]
