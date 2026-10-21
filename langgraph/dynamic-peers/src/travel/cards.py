"""AgentCards for the supervisor and each worker role."""

from __future__ import annotations

import os

from a2a.types.a2a_pb2 import AgentCapabilities, AgentCard, AgentInterface, AgentSkill
from a2a.utils.constants import PROTOCOL_VERSION_CURRENT, TransportProtocol

from travel.workers import EXTRA_SKILLS_ENV, WORKERS, Skill, extra_skills

def _card(name: str, description: str, skills: tuple[Skill, ...], examples: tuple[str, ...]) -> AgentCard:
    # URLs are placeholders for local dev; Kynomesh rewrites them in-cluster.
    return AgentCard(
        name=name,
        description=description,
        version="0.1.0",
        supported_interfaces=[
            AgentInterface(
                url="http://127.0.0.1:8088/a2a/jsonrpc",
                protocol_binding=TransportProtocol.JSONRPC.value,
                protocol_version=PROTOCOL_VERSION_CURRENT,
            ),
            AgentInterface(
                url="127.0.0.1:8089",
                protocol_binding=TransportProtocol.GRPC.value,
                protocol_version=PROTOCOL_VERSION_CURRENT,
            ),
        ],
        default_input_modes=["text"],
        default_output_modes=["text"],
        capabilities=AgentCapabilities(streaming=True),
        skills=[
            AgentSkill(id=s.id, name=s.name, description=s.description, tags=[s.id], examples=list(examples))
            for s in skills
        ],
    )


def supervisor_card() -> AgentCard:
    return _card(
        "Travel Planner",
        "Plans trips by delegating to whichever worker agents are deployed",
        (Skill("plan-trip", "Plan a trip", "Delegates to the available workers"),),
        ("Plan a weekend in Tokyo: flights from SFO and a hotel",),
    )


def worker_card(role: str) -> AgentCard:
    spec = WORKERS[role]
    skills = spec.skills + extra_skills(os.getenv(EXTRA_SKILLS_ENV, ""))
    return _card(role, spec.description, skills, spec.examples)
