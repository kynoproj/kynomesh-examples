import sys
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import AIMessage

from conftest import ScriptedChatModel
from kynomesh import client
from travel import main
from travel.discovery import WorkerInfo


def _llm(*texts: str) -> ScriptedChatModel:
    return ScriptedChatModel(responses=[AIMessage(content=t) for t in texts])


async def test_supervisor_agent_is_built_from_discovered_workers(caplog):
    workers = (WorkerInfo("flights", "Finds flights", ()),)
    caplog.set_level("INFO", logger="travel")

    with (
        patch.object(main, "discover_workers", AsyncMock(return_value=workers)),
        patch.object(main.supervisor_module, "build_llm", return_value=_llm("ok")),
    ):
        graph, card = await main.build_supervisor_agent()

    assert card.name == "Travel Planner"
    assert "discovered workers: ['flights']" in caplog.text
    result = await graph.ainvoke({"messages": [{"role": "user", "content": "hi"}]})
    assert result["messages"][-1].content == "ok"


async def test_worker_agent_uses_its_role_tools_and_card():
    with patch.object(main.supervisor_module, "build_llm", return_value=_llm("done")):
        graph, card = main.build_worker_agent("weather")

    assert card.name == "weather"
    result = await graph.ainvoke({"messages": [{"role": "user", "content": "hi"}]})
    assert result["messages"][-1].content == "done"


def test_missing_api_key_exits_with_message(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(sys, "argv", ["travel", "--role", "flights"])

    with pytest.raises(SystemExit, match="OPENAI_API_KEY"):
        main.main()


def test_supervisor_outside_kynomesh_exits_with_message(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.setattr(sys, "argv", ["travel", "--role", "planner"])

    async def no_topology(role):
        raise client.TopologyNotAvailableError

    monkeypatch.setattr(main, "serve", no_topology)

    with pytest.raises(SystemExit, match="no Kynomesh topology"):
        main.main()


def test_unknown_role_rejected(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["travel", "--role", "pilot"])
    with pytest.raises(SystemExit):
        main.main()


async def test_unreachable_worker_stops_startup_instead_of_serving_without_it(monkeypatch):
    from travel.discovery import PeerUnreachableError

    monkeypatch.setattr(
        main, "discover_workers", AsyncMock(side_effect=PeerUnreachableError("peer 'hotels' unreachable"))
    )

    with pytest.raises(PeerUnreachableError):  # the container exits, so Kubernetes restarts the pod
        await main.build_supervisor_agent()


def test_worker_gains_the_tool_of_an_enabled_extra_skill(monkeypatch):
    seen = {}

    def fake_create_agent(llm, tools, *, system_prompt):
        seen["tools"] = [t.name for t in tools]
        seen["prompt"] = system_prompt
        return object()

    monkeypatch.setattr(main, "create_agent", fake_create_agent)
    with patch.object(main.supervisor_module, "build_llm", return_value=_llm("x")):
        main.build_worker_agent("hotels")
        assert seen["tools"] == ["search_hotels"]
        assert "hotel_amenities" not in seen["prompt"]

        monkeypatch.setenv("EXTRA_SKILLS", "amenities")
        main.build_worker_agent("hotels")

    assert seen["tools"] == ["search_hotels", "hotel_amenities"]
    assert "hotel_amenities" in seen["prompt"]


def test_worker_refuses_to_start_with_an_unknown_extra_skill(monkeypatch):
    monkeypatch.setenv("EXTRA_SKILLS", "loyalty")

    with pytest.raises(ValueError, match="unknown extra skill"):
        main.build_worker_agent("hotels")
