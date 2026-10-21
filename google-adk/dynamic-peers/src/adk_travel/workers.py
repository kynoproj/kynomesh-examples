"""The worker roles this image can run. Which ones exist is decided by the AgentSet
manifest, not by the supervisor: it discovers whatever is deployed."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from adk_travel.tools import get_forecast, search_flights, search_hotels, hotel_amenities


@dataclass(frozen=True)
class Skill:
    id: str
    name: str
    description: str



EXTRA_SKILLS_ENV = "EXTRA_SKILLS"


@dataclass(frozen=True)
class ExtraSkill:
    skill: Skill
    tools: tuple  # the new capability: tools the worker gains while the skill is on
    guidance: str  # tells the worker when to use them


# Skills a worker can gain without a new image. Turning one on changes both the
# worker's AgentCard and what it can do, the way a new release of the agent would.
EXTRA_SKILL_CATALOG: dict[str, ExtraSkill] = {
    "amenities": ExtraSkill(
        Skill("amenities", "Amenities", "Lists a hotel's amenities, such as breakfast, wifi and pool"),
        (hotel_amenities,),
        "Use hotel_amenities to answer questions about a hotel's amenities, "
        "such as whether breakfast is included.",
    ),
}


def enabled_extra_skills(raw: str) -> tuple[ExtraSkill, ...]:
    """Parse a comma-separated list of skill ids, e.g. "amenities"."""
    ids = [part.strip() for part in raw.split(",") if part.strip()]
    unknown = [i for i in ids if i not in EXTRA_SKILL_CATALOG]
    if unknown:
        raise ValueError(f"unknown extra skill {unknown}; available: {sorted(EXTRA_SKILL_CATALOG)}")
    return tuple(EXTRA_SKILL_CATALOG[i] for i in ids)


def extra_skills(raw: str) -> tuple[Skill, ...]:
    """The AgentCard skills for the enabled extra skills."""
    return tuple(e.skill for e in enabled_extra_skills(raw))


def extra_tools(raw: str) -> tuple:
    """The tools the enabled extra skills add."""
    return tuple(t for e in enabled_extra_skills(raw) for t in e.tools)


def with_extra_skills(instruction: str, raw: str) -> str:
    """`instruction`, plus the guidance for each enabled extra skill."""
    return " ".join([instruction, *(e.guidance for e in enabled_extra_skills(raw))])


@dataclass(frozen=True)
class WorkerSpec:
    description: str
    instruction: str
    tools: tuple[Callable, ...]
    skills: tuple[Skill, ...]
    examples: tuple[str, ...]


WORKERS: dict[str, WorkerSpec] = {
    "flights": WorkerSpec(
        description="Finds flights between cities.",
        instruction="You are a flights expert. Use search_flights and report the options briefly.",
        tools=(search_flights,),
        skills=(Skill("search-flights", "Search flights", "Flight options with times and prices"),),
        examples=("Flights from SFO to Tokyo",),
    ),
    "hotels": WorkerSpec(
        description="Finds hotels in a city.",
        instruction="You are a hotels expert. Use search_hotels and report the options briefly.",
        tools=(search_hotels,),
        skills=(Skill("search-hotels", "Search hotels", "Hotel options with nightly prices"),),
        examples=("Hotels in Tokyo",),
    ),
    "weather": WorkerSpec(
        description="Gives the weekend weather forecast for a city.",
        instruction="You are a weather expert. Use get_forecast and report the forecast briefly.",
        tools=(get_forecast,),
        skills=(Skill("weekend-forecast", "Weekend forecast", "Saturday and Sunday forecast"),),
        examples=("Weather in Tokyo this weekend",),
    ),
}
