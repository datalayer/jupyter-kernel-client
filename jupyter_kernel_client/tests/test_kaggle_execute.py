# Copyright (c) 2023-2024 Datalayer, Inc.
#
# BSD 3-Clause License

from __future__ import annotations

import json
from pathlib import Path

import pytest

from jupyter_kernel_client.kaggle_execute import (
    KaggleExecutionResult,
    KaggleKernelExecutor,
    _normalize_status,
    _normalize_accelerator,
    _slugify,
)


class _FakeStatus:
    def __init__(self, status, failure_message=None):
        self.status = status
        self.failure_message = failure_message


class _FakePushResponse:
    url = "https://www.kaggle.com/code/me/my-notebook"
    version_number = 3


class _FakeApi:
    """Minimal stand-in for kaggle.api.kaggle_api_extended.KaggleApi."""

    def __init__(self, statuses, *, username="me"):
        self._statuses = list(statuses)
        self._username = username
        self.pushed_metadata = None
        self.pushed_code = None
        self.pushed_accelerator = None

    def get_config_value(self, name):
        return self._username if name == "username" else None

    def kernels_push(self, folder, accelerator=None):
        folder_path = Path(folder)
        self.pushed_metadata = json.loads(
            (folder_path / "kernel-metadata.json").read_text(encoding="utf-8")
        )
        code_file = self.pushed_metadata["code_file"]
        self.pushed_code = (folder_path / code_file).read_text(encoding="utf-8")
        self.pushed_accelerator = accelerator
        return _FakePushResponse()

    def kernels_status(self, slug):
        # Advance through the queued statuses, holding on the last one.
        status = self._statuses.pop(0) if len(self._statuses) > 1 else self._statuses[0]
        return _FakeStatus(status)

    def kernels_output(self, kernel, path, force=False, quiet=True):
        log_path = Path(path) / "run.log"
        log_path.write_text("execution log contents", encoding="utf-8")
        return ([str(log_path)], None)


def test_slugify_normalizes_title():
    assert _slugify("My Python Notebook!") == "my-python-notebook"
    assert _slugify("   ") .startswith("jkc-run-")


def test_normalize_status_handles_enum_like():
    class _Enum:
        name = "COMPLETE"

    assert _normalize_status(_Enum()) == "COMPLETE"
    assert _normalize_status("KernelWorkerStatus.ERROR") == "ERROR"
    assert _normalize_status("running") == "RUNNING"


def test_normalize_accelerator_supports_aliases():
    assert _normalize_accelerator("T4") == "NvidiaTeslaT4"
    assert _normalize_accelerator("tesla p100") == "NvidiaTeslaP100"
    assert _normalize_accelerator("NvidiaH100") == "NvidiaH100"


def test_normalize_accelerator_rejects_unknown_value():
    with pytest.raises(ValueError):
        _normalize_accelerator("SomeFutureGpu")


def test_execute_success_downloads_log():
    api = _FakeApi(["RUNNING", "COMPLETE"])
    executor = KaggleKernelExecutor(api=api)

    result = executor.execute(
        "print('hi')",
        title="My Python Notebook",
        poll_interval=0,
    )

    assert result.slug == "me/my-python-notebook"
    assert result.status == "COMPLETE"
    assert result.succeeded is True
    assert result.url == "https://www.kaggle.com/code/me/my-notebook"
    assert result.version_number == 3
    assert result.log == "execution log contents"

    # Metadata was written with the expected id and a notebook code file.
    assert api.pushed_metadata["id"] == "me/my-python-notebook"
    assert api.pushed_metadata["code_file"] == "notebook.ipynb"
    assert "print('hi')" in api.pushed_code

    notebook = json.loads(api.pushed_code)
    assert notebook["cells"][0]["id"]
    assert notebook["cells"][0]["metadata"]["language"] == "python"


def test_execute_script_kernel_writes_python_file():
    api = _FakeApi(["COMPLETE"])
    executor = KaggleKernelExecutor(api=api)

    executor.execute(
        "print('hi')",
        slug="my-script",
        kernel_type="script",
        poll_interval=0,
        download_output=False,
    )

    assert api.pushed_metadata["code_file"] == "script.py"
    assert api.pushed_metadata["kernel_type"] == "script"
    assert api.pushed_code == "print('hi')"


def test_execute_forwards_accelerator_and_enables_gpu_metadata():
    api = _FakeApi(["COMPLETE"])
    executor = KaggleKernelExecutor(api=api)

    executor.execute(
        "print('hi')",
        slug="my-notebook",
        accelerator="T4",
        poll_interval=0,
        download_output=False,
    )

    assert api.pushed_accelerator == "NvidiaTeslaT4"
    assert api.pushed_metadata["accelerator"] == "NvidiaTeslaT4"
    assert api.pushed_metadata["enable_gpu"] is True


def test_execute_without_wait_returns_current_status():
    api = _FakeApi(["QUEUED"])
    executor = KaggleKernelExecutor(api=api)

    result = executor.execute(
        "print('hi')",
        slug="my-notebook",
        wait=False,
    )

    assert result.slug == "me/my-notebook"
    assert result.status == "QUEUED"


def test_execute_times_out():
    api = _FakeApi(["RUNNING"])
    executor = KaggleKernelExecutor(api=api)

    result = executor.execute(
        "print('hi')",
        slug="stuck",
        timeout=0,
        poll_interval=0,
        download_output=False,
    )

    assert result.status == "RUNNING"


def test_missing_username_raises():
    api = _FakeApi(["COMPLETE"], username=None)
    executor = KaggleKernelExecutor(api=api)

    with pytest.raises(ValueError):
        executor.execute("print('hi')", poll_interval=0)


def test_explicit_username_is_used():
    api = _FakeApi(["COMPLETE"], username="ignored")
    executor = KaggleKernelExecutor(username="explicit", api=api)

    result = executor.execute(
        "print('hi')",
        slug="nb",
        poll_interval=0,
        download_output=False,
    )

    assert result.slug == "explicit/nb"


def test_to_kernel_reply_uses_notebook_outputs_when_available():
    result = {
        "cells": [
            {
                "cell_type": "code",
                "execution_count": 3,
                "outputs": [
                    {
                        "output_type": "stream",
                        "name": "stdout",
                            "text": "hello from kaggle\n",
                    }
                ],
            }
        ]
    }

    execution = KaggleExecutionResult(
        slug="me/demo",
        status="COMPLETE",
        notebook=result,
        log='[{"stream_name":"stderr","data":"infra warning\\n"}]',
    )

    reply = execution.to_kernel_reply()
    assert reply["status"] == "ok"
    assert reply["execution_count"] == 3
    assert reply["outputs"][0]["text"] == "hello from kaggle\n"


def test_to_kernel_reply_falls_back_to_log_streams():
    execution = KaggleExecutionResult(
        slug="me/demo",
        status="COMPLETE",
        log=(
            '['
            '{"stream_name":"stdout","data":"hello\\n"},'
            '{"stream_name":"stderr","data":"warn\\n"}'
            ']'
        ),
    )

    reply = execution.to_kernel_reply()
    assert reply["status"] == "ok"
    assert reply["execution_count"] == 0
    assert [output["name"] for output in reply["outputs"]] == ["stdout", "stderr"]


def test_stdout_stderr_and_repr_are_compact():
    execution = KaggleExecutionResult(
        slug="me/demo",
        status="COMPLETE",
        log=(
            '['
            '{"stream_name":"stdout","data":"hello\\n"},'
            '{"stream_name":"stderr","data":"warning\\n"}'
            ']'
        ),
    )

    assert execution.stdout == "hello\n"
    assert execution.stderr == "warning\n"
    rendered = repr(execution)
    assert "kernel_status='ok'" in rendered
    assert "stdout='hello'" in rendered
    assert "stderr='warning'" in rendered
