from unittest.mock import AsyncMock

from langchain_core.messages import AIMessage

from conftest import ScriptedChatModel, tool_call
from travel.discovery import WorkerInfo
from travel.supervisor import build_prompt, build_supervisor, peer_tools, tool_name

FLIGHTS = WorkerInfo("flights", "Finds flights", (("Search flights", "Times and prices"),))
HOTELS = WorkerInfo("hotels", "Finds hotels", ())
WEATHER = WorkerInfo("weather", "Weekend forecast", ())


def test_one_tool_per_worker_described_from_its_card():
    tools = peer_tools((FLIGHTS, HOTELS), AsyncMock())

    assert [t.name for t in tools] == ["ask_flights", "ask_hotels"]
    assert "Finds flights" in tools[0].description
    assert "Search flights: Times and prices" in tools[0].description


def test_tool_name_is_sanitized():
    assert tool_name("my worker.v2") == "ask_my_worker_v2"


def test_prompt_lists_exactly_the_discovered_workers():
    prompt = build_prompt((FLIGHTS, HOTELS))
    assert "ask_flights" in prompt and "ask_hotels" in prompt
    assert "ask_weather" not in prompt


def test_prompt_with_no_workers_says_so():
    assert "no workers" in build_prompt(())


async def test_adding_a_worker_needs_no_code_change():
    """Same supervisor code, a different discovered set: the new worker is callable."""
    ask_peer = AsyncMock(return_value="Sat: sunny")
    llm = ScriptedChatModel(
        responses=[tool_call("ask_weather", request="Tokyo weekend"), AIMessage(content="Sunny Saturday.")]
    )

    result = await build_supervisor(llm, (FLIGHTS, HOTELS, WEATHER), ask_peer).ainvoke(
        {"messages": [{"role": "user", "content": "weather in Tokyo?"}]}
    )

    ask_peer.assert_awaited_once_with("weather", "Tokyo weekend")
    assert result["messages"][-1].content == "Sunny Saturday."


async def test_supervisor_with_no_workers_still_answers():
    llm = ScriptedChatModel(responses=[AIMessage(content="I have no workers.")])

    result = await build_supervisor(llm, (), AsyncMock()).ainvoke(
        {"messages": [{"role": "user", "content": "hi"}]}
    )

    assert result["messages"][-1].content == "I have no workers."


async def test_failed_worker_is_reported_to_the_model_not_raised():
    ask_peer = AsyncMock(side_effect=ConnectionError("worker not up yet"))
    llm = ScriptedChatModel(
        responses=[tool_call("ask_flights", request="SFO to Tokyo"), AIMessage(content="Flights are unavailable.")]
    )

    result = await build_supervisor(llm, (FLIGHTS, HOTELS), ask_peer).ainvoke(
        {"messages": [{"role": "user", "content": "flights?"}]}
    )

    assert result["messages"][-1].content == "Flights are unavailable."
    tool_message = next(m for m in result["messages"] if m.type == "tool")
    assert tool_message.content == "Error: worker 'flights' failed: worker not up yet"
