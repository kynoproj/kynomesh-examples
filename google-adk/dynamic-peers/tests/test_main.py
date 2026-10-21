import sys
from unittest.mock import AsyncMock

import pytest

from adk_travel import main
from adk_travel.discovery import WorkerInfo


async def test_supervisor_agent_is_built_from_discovered_workers(monkeypatch, caplog):
    workers = (WorkerInfo("flights", "Finds flights", ()),)
    monkeypatch.setattr(main, "discover_workers", AsyncMock(return_value=workers))
    seen = {}

    async def fake_run_agent(prompt, *, runner):
        seen["runner"] = runner
        return "reply"

    monkeypatch.setattr(main, "run_agent", fake_run_agent)
    caplog.set_level("INFO", logger="adk_travel")

    run, card = await main.build_supervisor_agent()

    assert card.name == "Travel Planner"
    assert "discovered workers: ['flights']" in caplog.text
    assert await run("plan a trip") == "reply"
    assert [t.__name__ for t in seen["runner"].agent.tools] == ["ask_flights"]


async def test_worker_agent_uses_its_role_tools_and_card(monkeypatch):
    seen = {}

    async def fake_run_agent(prompt, *, runner):
        seen["runner"] = runner
        return "done"

    monkeypatch.setattr(main, "run_agent", fake_run_agent)

    run, card = main.build_worker_agent("weather")

    assert card.name == "weather"
    assert await run("hi") == "done"
    assert [t.__name__ for t in seen["runner"].agent.tools] == ["get_forecast"]


def test_missing_api_key_exits_with_message(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setattr(sys, "argv", ["x", "--role", "flights"])
    with pytest.raises(SystemExit, match="GOOGLE_API_KEY"):
        main.main()


def test_supervisor_outside_kynomesh_exits_with_message(monkeypatch):
    from kynomesh import client

    monkeypatch.setenv("GOOGLE_API_KEY", "x")
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
    from adk_travel.discovery import PeerUnreachableError

    monkeypatch.setattr(
        main, "discover_workers", AsyncMock(side_effect=PeerUnreachableError("peer 'hotels' unreachable"))
    )

    with pytest.raises(PeerUnreachableError):  # the container exits, so Kubernetes restarts the pod
        await main.build_supervisor_agent()
