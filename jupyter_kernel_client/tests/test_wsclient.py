# Copyright (c) 2023-2024 Datalayer, Inc.
#
# BSD 3-Clause License

import queue
from threading import Event
from unittest.mock import Mock
from urllib.parse import parse_qs, urlparse

import pytest

from jupyter_kernel_client import wsclient
from jupyter_kernel_client.wsclient import KernelWebSocketClient


def test_execute_interactive_raises_when_output_wait_times_out(monkeypatch):
    client = KernelWebSocketClient(endpoint="ws://example.test")
    client.connection_ready.set()
    client._iopub_channel = Mock()
    client._iopub_channel.is_alive.return_value = True
    client._iopub_channel.msg_ready.return_value = False
    client._iopub_channel.get_msg.side_effect = queue.Empty
    client._message_received = Mock()
    client._message_received.wait.return_value = False
    monkeypatch.setattr(client, "execute", Mock(return_value="message-id"))
    monkeypatch.setattr(wsclient.time, "monotonic", Mock(side_effect=(0.0, 0.05)))

    with pytest.raises(TimeoutError, match="Timeout waiting for output"):
        client.execute_interactive("pass", allow_stdin=False, timeout=0.1)

    client._message_received.wait.assert_called_once_with(timeout=pytest.approx(0.05))


def test_execute_interactive_does_not_lose_message_arriving_before_event_clear(monkeypatch):
    client = KernelWebSocketClient(endpoint="ws://example.test")
    client.connection_ready.set()
    client._message_received = Event()

    idle_message = {
        "parent_header": {"msg_id": "message-id"},
        "header": {"msg_type": "status"},
        "content": {"execution_state": "idle"},
    }
    messages = queue.Queue()
    ready_checks = 0

    def message_ready():
        nonlocal ready_checks
        ready_checks += 1
        if ready_checks == 2:
            # Simulate the websocket thread queueing a message after this
            # readiness check observed an empty queue but before Event.clear().
            was_ready = not messages.empty()
            messages.put(idle_message)
            client._message_received.set()
            return was_ready
        return not messages.empty()

    def execute(*args, **kwargs):
        client._message_received.set()
        return "message-id"

    client._iopub_channel = Mock()
    client._iopub_channel.is_alive.return_value = True
    client._iopub_channel.msg_ready.side_effect = message_ready
    client._iopub_channel.get_msg.side_effect = lambda timeout=0: messages.get_nowait()
    monkeypatch.setattr(client, "execute", execute)
    monkeypatch.setattr(client, "_recv_reply", Mock(return_value={"status": "ok"}))

    reply = client.execute_interactive("pass", allow_stdin=False, timeout=0.01, output_hook=Mock())

    assert reply == {"status": "ok"}
    assert messages.empty()


def test_start_channels_appends_extra_query_params_without_overriding_reserved(monkeypatch):
    captured: dict[str, object] = {}

    class DummySocket:
        def __init__(self, *args, **kwargs):
            captured["url"] = args[0]
            captured["header"] = kwargs.get("header")

        def close(self):
            return None

    class DummyThread:
        def __init__(self, *args, **kwargs):
            self._target = kwargs.get("target")

        def start(self):
            return None

        def is_alive(self):
            return False

        def join(self, timeout=None):
            return None

    monkeypatch.setattr(wsclient.websocket, "WebSocketApp", DummySocket)
    monkeypatch.setattr(wsclient, "Thread", DummyThread)

    client = KernelWebSocketClient(
        endpoint="ws://example.test/api/kernels/kernel-1/channels",
        token="real-token",
        timeout=0,
        extra_params={
            "runtime-proxy-token": "proxy-token",
            "token": "ignored-token",
            "session_id": "ignored-session",
        },
    )

    client.start_channels(shell=False, iopub=False, stdin=False, hb=False, control=False)

    parsed = parse_qs(urlparse(captured["url"]).query)
    assert parsed["token"] == ["real-token"]
    assert parsed["session_id"] == [client.session.session]
    assert parsed["runtime-proxy-token"] == ["proxy-token"]


def test_start_channels_ignores_reserved_extra_token_when_kernel_token_is_none(monkeypatch):
    captured: dict[str, object] = {}

    class DummySocket:
        def __init__(self, *args, **kwargs):
            captured["url"] = args[0]

        def close(self):
            return None

    class DummyThread:
        def __init__(self, *args, **kwargs):
            self._target = kwargs.get("target")

        def start(self):
            return None

        def is_alive(self):
            return False

        def join(self, timeout=None):
            return None

    monkeypatch.setattr(wsclient.websocket, "WebSocketApp", DummySocket)
    monkeypatch.setattr(wsclient, "Thread", DummyThread)

    client = KernelWebSocketClient(
        endpoint="ws://example.test/api/kernels/kernel-1/channels",
        token=None,
        timeout=0,
        extra_params={"token": "ignored-token", "extra": "x"},
    )

    client.start_channels(shell=False, iopub=False, stdin=False, hb=False, control=False)

    parsed = parse_qs(urlparse(captured["url"]).query)
    assert "token" not in parsed
    assert parsed["extra"] == ["x"]
