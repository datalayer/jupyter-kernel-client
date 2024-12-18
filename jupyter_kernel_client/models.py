from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VariableDescription:
    name: str
    type: tuple[str | None, str]
    size: int | None = None
