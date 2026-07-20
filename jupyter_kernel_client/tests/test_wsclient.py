# Copyright (c) 2023-2024 Datalayer, Inc.
#
# BSD 3-Clause License

import queue
from unittest.mock import Mock

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
