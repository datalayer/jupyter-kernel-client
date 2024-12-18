# Copyright (c) 2023-2024 Datalayer, Inc.
#
# BSD 3-Clause License

from __future__ import annotations

from typing import TypedDict


class VariableDescription(TypedDict):
    name: str
    type: tuple[str | None, str]
    size: int | None
