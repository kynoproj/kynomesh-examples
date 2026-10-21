import sys
from unittest.mock import AsyncMock

import pytest

from claude_travel import main
from claude_travel.discovery import WorkerInfo


async def test_supervisor_agent_is_built_from_discovered_workers(monkeypatch, caplog):
    workers = (WorkerInfo("flights", "Finds flights", ()),)
    monkeypatch.setattr(main, "discover_workers", AsyncMock(return_value=workers))
    seen = {}

    async def fake_run_agent(prompt, *, options):
        seen["prompt"], seen["options"] = prompt, options
        return "reply"

    monkeypatch.setattr(main, "run_agent", fake_run_agent)
    caplog.set_level("INFO", logger="claude_travel")

    run, card = await main.build_supervisor_agent()

    assert card.name == "Travel Planner"
    assert "discovered workers: ['flights']" in caplog.text
    assert await run("plan a trip") == "reply"
    assert seen["options"].allowed_tools == ["mcp__tools__ask_flights"]


async def test_worker_agent_uses_its_role_tools_and_card(monkeypatch):
    seen = {}

    async def fake_run_agent(prompt, *, options):
        seen["options"] = options
        return "done"

    monkeypatch.setattr(main, "run_agent", fake_run_agent)

    run, card = main.build_worker_agent("weather")

    assert card.name == "weather"
    assert await run("hi") == "done"
    assert seen["options"].allowed_tools == ["mcp__tools__get_forecast"]
    assert seen["options"].tools == []


def test_missing_api_key_exits_with_message(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(sys, "argv", ["x", "--role", "flights"])
    with pytest.raises(SystemExit, match="ANTHROPIC_API_KEY"):
        main.main()


def test_supervisor_outside_kynomesh_exits_with_message(monkeypatch):
    from kynomesh import client

    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.setattr(sys, "argv", ["x", "--role", "planner"])

    async def no_topology(role):
        raise client.TopologyNotAvailableError

    monkeypatch.setattr(main, "serve", no_topology)
    with pytest.raises(SystemExit, match="no Kynomesh topology"):
        main.main()


def test_unknown_role_rejected(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["x", "--role", "pilot"])
    with pytest.raises(SystemExit):
        main.main()


async def test_unreachable_worker_stops_startup_instead_of_serving_without_it(monkeypatch):
    from claude_travel.discovery import PeerUnreachableError

    monkeypatch.setattr(
        main, "discover_workers", AsyncMock(side_effect=PeerUnreachableError("peer 'hotels' unreachable"))
    )

    with pytest.raises(PeerUnreachableError):  # the container exits, so Kubernetes restarts the pod
        await main.build_supervisor_agent()


async def test_worker_gains_the_behavior_of_an_enabled_extra_skill(monkeypatch):
    seen = {}

    async def fake_run_agent(prompt, *, options):
        seen["options"] = options
        return "done"

    monkeypatch.setattr(main, "run_agent", fake_run_agent)

    plain, _ = main.build_worker_agent("hotels")
    await plain("hi")
    assert "cheapest option" not in seen["options"].system_prompt

    monkeypatch.setenv("EXTRA_SKILLS", "price-comparison")
    boosted, _ = main.build_worker_agent("hotels")
    await boosted("hi")

    assert "cheapest option" in seen["options"].system_prompt


def test_worker_refuses_to_start_with_an_unknown_extra_skill(monkeypatch):
    monkeypatch.setenv("EXTRA_SKILLS", "loyalty")

    with pytest.raises(ValueError, match="unknown extra skill"):
        main.build_worker_agent("hotels")
