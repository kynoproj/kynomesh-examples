import pytest

from claude_travel.cards import supervisor_card, worker_card
from claude_travel.tools import get_forecast, search_flights, search_hotels
from claude_travel.workers import WORKERS, extra_skills, extra_tools, with_extra_skills

def _name(tool):
    return getattr(tool, "name", None) or tool.__name__


async def test_tools_return_stub_data():
    flights = await search_flights.handler({"origin": "SFO", "destination": "Tokyo"})
    hotels = await search_hotels.handler({"city": "tokyo"})
    forecast = await get_forecast.handler({"city": "Tokyo"})

    assert "NH7" in flights["content"][0]["text"]
    assert "Shinjuku" in hotels["content"][0]["text"]
    assert "rain" in forecast["content"][0]["text"]


async def test_unknown_city_is_a_normal_reply_not_an_error():
    result = await search_hotels.handler({"city": "Atlantis"})
    assert "No hotels" in result["content"][0]["text"]
    assert "is_error" not in result


@pytest.mark.parametrize("tool", [search_flights, search_hotels, get_forecast])
async def test_missing_argument_is_reported_to_the_model(tool):
    result = await tool.handler({})
    assert result["is_error"] is True


@pytest.mark.parametrize("role", WORKERS)
def test_worker_cards_advertise_their_skills_and_protocol_version(role):
    card = worker_card(role)
    assert card.name == role
    assert [s.id for s in card.skills] == [s.id for s in WORKERS[role].skills]
    assert all(i.protocol_version for i in card.supported_interfaces)


def test_extra_skill_env_changes_the_card(monkeypatch):
    base = worker_card("hotels")
    monkeypatch.setenv("EXTRA_SKILLS", "amenities")

    changed = worker_card("hotels")

    added = changed.skills[-1]
    assert [s.id for s in changed.skills][:-1] == [s.id for s in base.skills]
    assert added.id == "amenities"
    assert added.name == "Amenities"
    assert "breakfast" in added.description
    assert changed != base


def test_extra_skill_gives_the_worker_a_new_tool_and_guidance():
    base = "You are a hotels expert."

    assert extra_tools("") == ()
    assert [_name(t) for t in extra_tools("amenities")] == ["hotel_amenities"]
    assert with_extra_skills(base, "") == base
    assert "hotel_amenities" in with_extra_skills(base, "amenities")


def test_unknown_extra_skill_is_rejected_instead_of_advertising_a_skill_it_lacks():
    with pytest.raises(ValueError, match="unknown extra skill.*loyalty.*amenities"):
        extra_skills("amenities, loyalty")


def test_extra_skills_ignores_blanks():
    assert extra_skills(" , ") == ()


def test_supervisor_card_has_a_skill():
    assert supervisor_card().skills
