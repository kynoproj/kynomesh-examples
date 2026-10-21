"""AgentCards, one per role."""

from __future__ import annotations

from a2a.types.a2a_pb2 import (
    AgentCapabilities,
    AgentCard,
    AgentInterface,
    AgentSkill,
)
from a2a.utils.constants import PROTOCOL_VERSION_CURRENT, TransportProtocol

ROLES = ("assistant", "researcher", "calculator")

_DESCRIPTIONS = {
    "assistant": ("Assistant", "Delegates questions to the researcher and calculator agents"),
    "researcher": ("Researcher", "Answers factual questions from a small knowledge base"),
    "calculator": ("Calculator", "Solves arithmetic problems"),
}
_EXAMPLES = {
    "assistant": ["What is the population of France multiplied by 3?"],
    "researcher": ["Tell me about Japan"],
    "calculator": ["What is 68 * 3?"],
}


def agent_card(role: str) -> AgentCard:
    if role not in ROLES:
        raise ValueError(f"unknown role {role!r}; expected one of {ROLES}")
    name, description = _DESCRIPTIONS[role]
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
            AgentSkill(
                id=role,
                name=name,
                description=description,
                tags=[role],
                examples=_EXAMPLES[role],
            )
        ],
    )
