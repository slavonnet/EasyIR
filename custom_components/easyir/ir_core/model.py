"""Transport-agnostic canonical IR frame."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class CanonicalIRFrame:
    """Normalized IR transmission intent (codec / transport adapters consume this).

    Field semantics follow docs/roadmap.multi-agent.yaml (canonical_model.required_fields).
    Unknown physical-layer parameters are represented with None and/or empty metadata.
    """

    timings: list[int]
    carrier_frequency_hz: float | None = None
    repeat: int = 0
    duty_cycle: float | None = None
    protocol_hint: str = "unknown"
    integrity_metadata: dict[str, Any] = field(default_factory=dict)
    decode_confidence: float | None = None
    unknown_fields: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.timings, list):
            raise TypeError("timings must be a list of integers")
        object.__setattr__(self, "timings", [int(x) for x in self.timings])
