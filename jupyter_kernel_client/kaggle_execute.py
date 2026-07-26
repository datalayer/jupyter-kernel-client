# Copyright (c) 2023-2024 Datalayer, Inc.
#
# BSD 3-Clause License

"""Run code on Kaggle through the official *kernels* (notebooks) API.

Unlike :class:`~jupyter_kernel_client.kaggle.KaggleKernelClient`, which connects
to an **already-running** interactive Kaggle notebook session over websocket,
this module drives Kaggle's **batch** kernels API: it creates (or updates) a
Kaggle notebook, runs it end to end on Kaggle's infrastructure, waits for
completion, and downloads the output. This is the supported "from zero" way to
create a Kaggle kernel and run code from a standalone process — no browser
session is required, only Kaggle API credentials.

Authentication is delegated to the official ``kaggle`` package, which resolves
credentials from (in order) the ``KAGGLE_USERNAME`` / ``KAGGLE_KEY`` environment
variables, a ``KAGGLE_API_TOKEN`` (newer CLIs), or a ``~/.kaggle/kaggle.json``
file. Install the optional dependency with
``pip install 'jupyter-kernel-client[kaggle]'``.

Example:
    >>> from jupyter_kernel_client import KaggleKernelExecutor
    >>> executor = KaggleKernelExecutor()  # credentials from the environment
    >>> result = executor.execute(
    ...     "import pandas as pd\\nprint('Running on Kaggle')",
    ...     title="My Python Notebook",
    ... )
    >>> print(result.status)  # e.g. "COMPLETE"
    >>> print(result.log)     # captured execution log
"""

from __future__ import annotations

import json
import logging
import re
import tempfile
import time
import typing as t
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from jupyter_kernel_client.log import get_logger

if t.TYPE_CHECKING:  # pragma: no cover - typing only
    from kaggle.api.kaggle_api_extended import KaggleApi

#: Kernel statuses that indicate execution has finished (successfully or not).
TERMINAL_STATUSES: frozenset[str] = frozenset({"COMPLETE", "ERROR", "CANCEL_ACKNOWLEDGED"})
#: Default number of seconds to wait for a Kaggle run to finish.
DEFAULT_EXECUTION_TIMEOUT = 3600.0
#: Default number of seconds between status polls.
DEFAULT_POLL_INTERVAL = 10.0

_SLUG_CLEAN_RE = re.compile(r"[^a-z0-9]+")

_KAGGLE_ACCELERATOR_ALIASES: dict[str, str] = {
    "tesla p100": "NvidiaTeslaP100",
    "nvidiateslap100": "NvidiaTeslaP100",
    "p100": "NvidiaTeslaP100",
    "tesla t4": "NvidiaTeslaT4",
    "nvidiateslat4": "NvidiaTeslaT4",
    "t4": "NvidiaTeslaT4",
    "tesla t4 high memory": "NvidiaTeslaT4Highmem",
    "nvidiateslat4highmem": "NvidiaTeslaT4Highmem",
    "t4 high memory": "NvidiaTeslaT4Highmem",
    "t4highmem": "NvidiaTeslaT4Highmem",
    "l4": "NvidiaL4",
    "nvidial4": "NvidiaL4",
    "l4 x1": "NvidiaL4X1",
    "nvidial4x1": "NvidiaL4X1",
    "l4x1": "NvidiaL4X1",
    "a100": "NvidiaTeslaA100",
    "nvidiateslaa100": "NvidiaTeslaA100",
    "h100": "NvidiaH100",
    "nvidiah100": "NvidiaH100",
    "rtx pro 6000": "NvidiaRtxPro6000",
    "nvidiartxpro6000": "NvidiaRtxPro6000",
    "rtxpro6000": "NvidiaRtxPro6000",
}

_KAGGLE_ACCELERATOR_VALUES = sorted(set(_KAGGLE_ACCELERATOR_ALIASES.values()))


def _slugify(value: str) -> str:
    """Turn an arbitrary title into a Kaggle-compatible slug."""
    slug = _SLUG_CLEAN_RE.sub("-", value.strip().lower()).strip("-")
    return slug or f"jkc-run-{uuid.uuid4().hex[:8]}"


def _normalize_status(status: t.Any) -> str:
    """Normalize a Kaggle status value (enum, int or string) to a plain name."""
    name = getattr(status, "name", None)
    if name is None:
        name = str(status)
    return name.split(".")[-1].strip().upper()


def _build_notebook(code: str) -> dict[str, t.Any]:
    """Build a minimal nbformat v4 notebook with a single code cell."""
    return {
        "cells": [
            {
                "cell_type": "code",
                "id": uuid.uuid4().hex[:8],
                "metadata": {"language": "python"},
                "execution_count": None,
                "outputs": [],
                "source": code,
            }
        ],
        "metadata": {
            "kernelspec": {
                "name": "python3",
                "display_name": "Python 3",
                "language": "python",
            },
            "language_info": {"name": "python"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def _normalize_accelerator(accelerator: str | None) -> str | None:
    """Normalize human-friendly accelerator names to Kaggle API values."""
    if accelerator is None:
        return None
    normalized = accelerator.strip()
    if not normalized:
        return None
    alias_key = normalized.lower()
    resolved = _KAGGLE_ACCELERATOR_ALIASES.get(alias_key)
    if resolved is None:
        raise ValueError(
            "Unsupported Kaggle accelerator {!r}. Supported values: {}".format(
                accelerator,
                ", ".join(_KAGGLE_ACCELERATOR_VALUES),
            )
        )
    return resolved


@dataclass
class KaggleExecutionResult:
    """Outcome of running code on Kaggle through the kernels API."""

    #: Full kernel reference, ``"<owner>/<slug>"``.
    slug: str
    #: Normalized final status, e.g. ``"COMPLETE"`` or ``"ERROR"``.
    status: str
    #: Kaggle notebook URL, when known.
    url: str | None = None
    #: Kernel version number produced by the push, when known.
    version_number: int | None = None
    #: Failure message reported by Kaggle, when the run did not succeed.
    failure_message: str | None = None
    #: Directory the outputs were downloaded to, when ``download_output=True``.
    output_dir: str | None = None
    #: Paths of downloaded output files.
    output_files: list[str] = field(default_factory=list)
    #: Contents of the execution ``.log`` file, when present.
    log: str | None = None
    #: The executed notebook (nbformat dict), when present in the output.
    notebook: dict[str, t.Any] | None = None
    #: Jupyter-style execute reply derived from the notebook/log output.
    kernel_reply: dict[str, t.Any] | None = None

    @property
    def succeeded(self) -> bool:
        """Whether the run finished with a ``COMPLETE`` status."""
        return self.status == "COMPLETE"

    @property
    def outputs(self) -> list[dict[str, t.Any]]:
        """Jupyter-like output list for the execution."""
        reply = self.kernel_reply or self.to_kernel_reply()
        return list(reply.get("outputs", []))

    @property
    def stdout(self) -> str:
        """Merged stdout stream extracted from kernel-like outputs."""
        chunks: list[str] = []
        for output in self.outputs:
            if output.get("output_type") == "stream" and output.get("name") == "stdout":
                chunks.append(str(output.get("text", "")))
        return "".join(chunks)

    @property
    def stderr(self) -> str:
        """Merged stderr stream extracted from kernel-like outputs."""
        chunks: list[str] = []
        for output in self.outputs:
            if output.get("output_type") == "stream" and output.get("name") == "stderr":
                chunks.append(str(output.get("text", "")))
        return "".join(chunks)

    def __repr__(self) -> str:
        """Compact representation that avoids printing full raw logs."""
        reply = self.kernel_reply or self.to_kernel_reply()
        return (
            "KaggleExecutionResult("
            f"slug={self.slug!r}, status={self.status!r}, kernel_status={reply.get('status')!r}, "
            f"url={self.url!r}, version_number={self.version_number!r}, "
            f"execution_count={reply.get('execution_count', 0)!r}, "
            f"stdout={self.stdout.strip()!r}, stderr={self.stderr.strip()!r}, "
            f"failure_message={self.failure_message!r}, output_dir={self.output_dir!r}, "
            f"output_files={self.output_files!r}"
            ")"
        )

    def to_kernel_reply(self) -> dict[str, t.Any]:
        """Return a Jupyter-like execute reply.

        This mirrors the shape returned by ``JupyterKernelClient.execute``:
        ``{"execution_count": int, "outputs": list, "status": "ok"|"error"}``.
        """
        outputs: list[dict[str, t.Any]] = []
        execution_count = 0

        if self.notebook:
            outputs, execution_count = _extract_notebook_outputs(self.notebook)

        if not outputs and self.log:
            outputs = _outputs_from_kaggle_log(self.log)

        has_error_output = any(output.get("output_type") == "error" for output in outputs)
        status = "ok" if (self.succeeded and not has_error_output) else "error"

        return {
            "execution_count": execution_count,
            "outputs": outputs,
            "status": status,
        }


def _extract_notebook_outputs(notebook: dict[str, t.Any]) -> tuple[list[dict[str, t.Any]], int]:
    """Extract outputs from the last executed code cell in an nbformat dict."""
    execution_count = 0
    outputs: list[dict[str, t.Any]] = []

    for cell in notebook.get("cells", []):
        if cell.get("cell_type") != "code":
            continue
        cell_outputs = cell.get("outputs") or []
        if not cell_outputs:
            continue
        outputs = [
            output for output in cell_outputs if isinstance(output, dict) and "output_type" in output
        ]
        count = cell.get("execution_count")
        execution_count = count if isinstance(count, int) else execution_count

    return outputs, execution_count


def _outputs_from_kaggle_log(log: str) -> list[dict[str, t.Any]]:
    """Convert Kaggle log stream events into Jupyter stream outputs."""
    if not log.strip():
        return []

    events: list[dict[str, t.Any]] = []
    try:
        parsed = json.loads(log)
        if isinstance(parsed, list):
            events = [event for event in parsed if isinstance(event, dict)]
    except ValueError:
        # Keep plain-text fallback for unexpected log formats.
        return [{"output_type": "stream", "name": "stdout", "text": log}]

    outputs: list[dict[str, t.Any]] = []
    for event in events:
        stream_name = str(event.get("stream_name", "stdout")).strip().lower()
        if stream_name not in {"stdout", "stderr"}:
            stream_name = "stdout"
        text = event.get("data")
        if text is None:
            continue
        outputs.append(
            {
                "output_type": "stream",
                "name": stream_name,
                "text": str(text),
            }
        )

    return outputs


class KaggleKernelExecutor:
    """Create and run Kaggle notebooks (kernels) through the official API.

    Args:
        username: Kaggle username used to build the kernel reference
            (``"<username>/<slug>"``). When omitted, it is read from the
            authenticated Kaggle configuration.
        api: An already-authenticated ``KaggleApi`` instance. When omitted, one
            is created and authenticated lazily on first use.
        quiet: Whether to suppress the Kaggle client's own progress output.
        log: Optional logger.
    """

    def __init__(
        self,
        username: str | None = None,
        *,
        api: KaggleApi | None = None,
        quiet: bool = True,
        log: logging.Logger | None = None,
    ) -> None:
        self._username = username
        self._api = api
        self._quiet = quiet
        self.log = log or get_logger()

    # -- Kaggle client ---------------------------------------------------

    @property
    def api(self) -> KaggleApi:
        """The authenticated Kaggle API client (created lazily)."""
        if self._api is None:
            try:
                from kaggle.api.kaggle_api_extended import KaggleApi
            except ImportError as exc:  # pragma: no cover - optional dependency
                raise ImportError(
                    "The 'kaggle' package is required for KaggleKernelExecutor. "
                    "Install it with: pip install 'jupyter-kernel-client[kaggle]'"
                ) from exc
            api = KaggleApi()
            api.authenticate()
            self._api = api
        return self._api

    def _resolve_username(self) -> str:
        if self._username:
            return self._username
        username = self.api.get_config_value("username")
        if not username:
            raise ValueError(
                "Could not determine the Kaggle username. Pass 'username=...' or "
                "configure Kaggle credentials (KAGGLE_USERNAME / kaggle.json)."
            )
        self._username = username
        return username

    # -- Public API ------------------------------------------------------

    def execute(
        self,
        code: str,
        *,
        slug: str | None = None,
        title: str | None = None,
        language: str = "python",
        kernel_type: str = "notebook",
        enable_gpu: bool = False,
        accelerator: str | None = None,
        enable_internet: bool = True,
        is_private: bool = True,
        dataset_sources: t.Sequence[str] | None = None,
        competition_sources: t.Sequence[str] | None = None,
        kernel_sources: t.Sequence[str] | None = None,
        model_sources: t.Sequence[str] | None = None,
        wait: bool = True,
        timeout: float = DEFAULT_EXECUTION_TIMEOUT,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        download_output: bool = True,
        output_dir: str | None = None,
    ) -> KaggleExecutionResult:
        """Create (or update) a Kaggle notebook, run it, and collect the output.

        Args:
            code: The Python (or R) source to run in a single notebook cell.
            slug: Kaggle notebook slug. Generated from ``title`` (or a random
                value) when omitted. Reusing a slug creates a new version.
            title: Human-readable notebook title. Defaults to the slug.
            language: Notebook language (``"python"`` or ``"r"``).
            kernel_type: ``"notebook"`` or ``"script"``.
            enable_gpu: Whether to request a GPU.
            accelerator: Explicit Kaggle accelerator value, for example
                ``"NvidiaTeslaT4"`` or ``"NvidiaTeslaP100"``. Friendly aliases
                such as ``"T4"`` and ``"P100"`` are also accepted. When set, GPU
                is enabled automatically.
            enable_internet: Whether the kernel may access the internet.
            is_private: Whether the notebook is private.
            dataset_sources: Kaggle dataset references to attach.
            competition_sources: Kaggle competition references to attach.
            kernel_sources: Kaggle kernel references to attach.
            model_sources: Kaggle model references to attach.
            wait: Whether to block until the run reaches a terminal status.
            timeout: Maximum seconds to wait for completion.
            poll_interval: Seconds between status polls.
            download_output: Whether to download outputs after completion.
            output_dir: Directory to download outputs into. A temporary
                directory is used when omitted.

        Returns:
            A :class:`KaggleExecutionResult` describing the run.
        """
        username = self._resolve_username()
        slug = slug or _slugify(title or f"jkc-run-{uuid.uuid4().hex[:8]}")
        ref = f"{username}/{slug}"
        title = title or slug
        normalized_accelerator = _normalize_accelerator(accelerator)
        resolved_enable_gpu = bool(enable_gpu or normalized_accelerator)

        with tempfile.TemporaryDirectory(prefix="jkc-kaggle-") as tmp:
            folder = Path(tmp)
            code_file = self._write_sources(folder, code, kernel_type, language)
            self._write_metadata(
                folder,
                ref=ref,
                title=title,
                code_file=code_file,
                language=language,
                kernel_type=kernel_type,
                enable_gpu=resolved_enable_gpu,
                accelerator=normalized_accelerator,
                enable_internet=enable_internet,
                is_private=is_private,
                dataset_sources=dataset_sources,
                competition_sources=competition_sources,
                kernel_sources=kernel_sources,
                model_sources=model_sources,
            )

            self.log.info("Pushing Kaggle kernel %s", ref)
            push_response = self._kernels_push(str(folder), normalized_accelerator)

        url = getattr(push_response, "url", None)
        version_number = getattr(push_response, "version_number", None)

        result = KaggleExecutionResult(
            slug=ref,
            status="QUEUED",
            url=url,
            version_number=version_number,
        )

        if not wait:
            result.status = self.status(ref)
            return result

        result.status, result.failure_message = self._wait_for_completion(
            ref, timeout=timeout, poll_interval=poll_interval
        )

        if download_output:
            self._download_output(ref, result, output_dir)

        result.kernel_reply = result.to_kernel_reply()

        return result

    def status(self, slug: str) -> str:
        """Return the normalized status of a Kaggle kernel."""
        response = self.api.kernels_status(slug)
        return _normalize_status(getattr(response, "status", response))

    def output(
        self,
        slug: str,
        dest: str,
        *,
        force: bool = True,
        quiet: bool | None = None,
    ) -> list[str]:
        """Download a kernel's output files into ``dest`` and return their paths."""
        Path(dest).mkdir(parents=True, exist_ok=True)
        quiet = self._quiet if quiet is None else quiet
        files, _token = self.api.kernels_output(slug, path=dest, force=force, quiet=quiet)
        return list(files)

    # -- Internals -------------------------------------------------------

    @staticmethod
    def _write_sources(folder: Path, code: str, kernel_type: str, language: str) -> str:
        if kernel_type == "script":
            extension = "r" if language == "r" else "py"
            code_file = f"script.{extension}"
            (folder / code_file).write_text(code, encoding="utf-8")
        else:
            code_file = "notebook.ipynb"
            (folder / code_file).write_text(
                json.dumps(_build_notebook(code), indent=1), encoding="utf-8"
            )
        return code_file

    @staticmethod
    def _write_metadata(
        folder: Path,
        *,
        ref: str,
        title: str,
        code_file: str,
        language: str,
        kernel_type: str,
        enable_gpu: bool,
        accelerator: str | None,
        enable_internet: bool,
        is_private: bool,
        dataset_sources: t.Sequence[str] | None,
        competition_sources: t.Sequence[str] | None,
        kernel_sources: t.Sequence[str] | None,
        model_sources: t.Sequence[str] | None,
    ) -> None:
        metadata = {
            "id": ref,
            "title": title,
            "code_file": code_file,
            "language": language,
            "kernel_type": kernel_type,
            "is_private": is_private,
            "enable_gpu": enable_gpu,
            "enable_internet": enable_internet,
            "dataset_sources": list(dataset_sources or []),
            "competition_sources": list(competition_sources or []),
            "kernel_sources": list(kernel_sources or []),
            "model_sources": list(model_sources or []),
        }
        if accelerator:
            metadata["accelerator"] = accelerator
        (folder / "kernel-metadata.json").write_text(
            json.dumps(metadata, indent=2), encoding="utf-8"
        )

    def _kernels_push(self, folder: str, accelerator: str | None):
        if accelerator is None:
            return self.api.kernels_push(folder)
        try:
            return self.api.kernels_push(folder, accelerator=accelerator)
        except TypeError:
            # Older kaggle clients may not expose the accelerator kwarg yet.
            return self.api.kernels_push(folder)

    def _wait_for_completion(
        self,
        slug: str,
        *,
        timeout: float,
        poll_interval: float,
    ) -> tuple[str, str | None]:
        deadline = time.monotonic() + timeout
        status = "QUEUED"
        failure_message: str | None = None
        while True:
            response = self.api.kernels_status(slug)
            status = _normalize_status(getattr(response, "status", response))
            failure_message = getattr(response, "failure_message", None) or None
            self.log.debug("Kaggle kernel %s status: %s", slug, status)
            if status in TERMINAL_STATUSES:
                break
            if time.monotonic() >= deadline:
                self.log.warning("Timed out waiting for Kaggle kernel %s", slug)
                break
            time.sleep(poll_interval)
        return status, failure_message

    def _download_output(
        self,
        slug: str,
        result: KaggleExecutionResult,
        output_dir: str | None,
    ) -> None:
        try:
            if output_dir is None:
                output_dir = tempfile.mkdtemp(prefix="jkc-kaggle-out-")
            files = self.output(slug, output_dir)
            result.output_dir = output_dir
            result.output_files = files
            self._populate_log_and_notebook(result, files)
        except Exception as exc:  # pragma: no cover - best-effort download
            self.log.warning("Could not download Kaggle output for %s: %s", slug, exc)

    @staticmethod
    def _populate_log_and_notebook(
        result: KaggleExecutionResult, files: t.Sequence[str]
    ) -> None:
        for path_str in files:
            path = Path(path_str)
            if path.suffix == ".log" and result.log is None:
                try:
                    result.log = path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    pass
            elif path.suffix == ".ipynb" and result.notebook is None:
                try:
                    result.notebook = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    pass
