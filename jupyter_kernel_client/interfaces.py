# Copyright (c) 2023-2024 Datalayer, Inc.
#
# BSD 3-Clause License

"""Typing protocols for kernel client implementations."""

from __future__ import annotations

import datetime
import typing as t
from typing import Protocol, runtime_checkable

from jupyter_kernel_client.models import VariableDescription


@runtime_checkable
class IKernelClient(Protocol):
    """Protocol describing the public KernelClient interface."""

    @property
    def execution_state(self) -> str | None: ...

    @property
    def has_kernel(self) -> bool: ...

    @property
    def id(self) -> str | None: ...

    @property
    def kernel_info(self) -> dict[str, t.Any] | None: ...

    @property
    def last_activity(self) -> datetime.datetime | None: ...

    def list_kernels(self) -> list[dict[str, t.Any]]: ...

    @property
    def username(self) -> str: ...

    @property
    def server_url(self) -> str: ...

    def execute(
        self,
        code: str,
        silent: bool = False,
        store_history: bool = True,
        user_expressions: dict[str, t.Any] | None = None,
        allow_stdin: bool | None = False,
        stop_on_error: bool = True,
        timeout: float = 60.0,
        stdin_hook: t.Callable[[dict[str, t.Any]], None] | None = None,
        variables: dict[str, t.Any] | None = None,
    ) -> dict[str, t.Any]: ...

    def execute_interactive(
        self,
        code: str,
        silent: bool = False,
        store_history: bool = True,
        user_expressions: dict[str, t.Any] | None = None,
        allow_stdin: bool | None = None,
        stop_on_error: bool = True,
        timeout: float | None = 60.0,
        output_hook: t.Callable[[dict[str, t.Any]], None] | None = None,
        stdin_hook: t.Callable[[dict[str, t.Any]], None] | None = None,
        variables: dict[str, t.Any] | None = None,
    ) -> dict[str, t.Any]: ...

    def interrupt(self, timeout: float = 60.0) -> None: ...

    def is_alive(self, timeout: float = 60.0) -> bool: ...

    def restart(self, timeout: float = 60.0) -> None: ...

    def __enter__(self) -> IKernelClient: ...

    def __exit__(self, exc_type, exc_value, exc_tb) -> None: ...

    def start(self, name: str = "python3", path: str | None = None, timeout: float = 60.0) -> None: ...

    def stop(
        self,
        shutdown_kernel: bool | None = None,
        shutdown_now: bool = True,
        timeout: float = 60.0,
    ) -> None: ...

    def set_variable(self, name: str, value: t.Any) -> None: ...

    def get_variable(self, name: str) -> tuple[dict[str, t.Any], dict[str, t.Any]]: ...

    def list_variables(self) -> list[VariableDescription]: ...

    def get_variable_mimetypes(
        self, name: str, mimetype: str | None = None
    ) -> tuple[dict[str, t.Any], dict[str, t.Any]]: ...
