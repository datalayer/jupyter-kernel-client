# Copyright (c) 2023-2024 Datalayer, Inc.
#
# BSD 3-Clause License

"""A process holding an open, never closed, kernel client must still exit."""

import base64
import hashlib
import socket
import subprocess
import sys
import textwrap
import threading
import time

import pytest

from jupyter_kernel_client.wsclient import KernelWebSocketClient

_WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


class _HoldingWebSocketServer:
    """Accept websocket handshakes, then keep every connection open, silent."""

    def __init__(self) -> None:
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen()
        self.port = self._sock.getsockname()[1]
        self.handshakes = 0
        self._conns: list[socket.socket] = []
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    @property
    def endpoint(self) -> str:
        return f"ws://127.0.0.1:{self.port}/api/kernels/k/channels"

    def _serve(self) -> None:
        while True:
            try:
                conn, _ = self._sock.accept()
            except OSError:
                return
            self._conns.append(conn)
            request = b""
            while b"\r\n\r\n" not in request:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                request += chunk
            key = ""
            for line in request.decode("latin-1").split("\r\n"):
                if line.lower().startswith("sec-websocket-key:"):
                    key = line.split(":", 1)[1].strip()
            accept = base64.b64encode(
                hashlib.sha1((key + _WS_GUID).encode()).digest()  # noqa: S324
            ).decode()
            conn.sendall(
                (
                    "HTTP/1.1 101 Switching Protocols\r\n"
                    "Upgrade: websocket\r\n"
                    "Connection: Upgrade\r\n"
                    f"Sec-WebSocket-Accept: {accept}\r\n\r\n"
                ).encode()
            )
            self.handshakes += 1

    def close(self) -> None:
        self._sock.close()
        for conn in self._conns:
            conn.close()


@pytest.fixture
def ws_server():
    server = _HoldingWebSocketServer()
    yield server
    server.close()


def test_process_with_unclosed_client_exits(ws_server):
    script = textwrap.dedent(
        f"""
        from jupyter_kernel_client.wsclient import KernelWebSocketClient

        client = KernelWebSocketClient(endpoint={ws_server.endpoint!r}, timeout=5)
        client.start_channels(shell=False, iopub=False, stdin=False, hb=False, control=False)
        assert client.connection_ready.is_set(), "websocket did not open"
        assert client.connection_thread.daemon
        # No stop_channels(): the interpreter must still be able to exit.
        print("connected", flush=True)
        """
    )
    proc = subprocess.run(  # noqa: S603
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert proc.returncode == 0, proc.stderr
    assert "connected" in proc.stdout
    assert ws_server.handshakes == 1


def test_stop_channels_joins_the_websocket_thread(ws_server):
    client = KernelWebSocketClient(endpoint=ws_server.endpoint, timeout=5)
    client.start_channels(shell=False, iopub=False, stdin=False, hb=False, control=False)
    assert client.connection_ready.is_set()
    thread = client.connection_thread
    assert thread is not None and thread.daemon and thread.is_alive()

    started = time.monotonic()
    client.stop_channels()

    # The listener wakes on the socket shutdown; no wait for the join timeout.
    assert time.monotonic() - started < 2
    assert not thread.is_alive()
    assert client.connection_thread is None
    assert client.kernel_socket is None


def _open_client(ws_server, **kwargs):
    client = KernelWebSocketClient(endpoint=ws_server.endpoint, timeout=5, **kwargs)
    client.start_channels(shell=False, iopub=False, stdin=False, hb=False, control=False)
    assert client.connection_ready.is_set(), "websocket did not open"
    return client


def _wait_until_lost(client, seconds):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if not client.connection_ready.is_set():
            return True
        time.sleep(0.05)
    return False


def test_unanswered_ping_marks_the_connection_lost(ws_server):
    # The server keeps the TCP connection open and never answers a ping, as a
    # half-open connection does.
    client = _open_client(ws_server, ping_interval=1, ping_timeout=0.5)
    try:
        assert _wait_until_lost(client, 6), "a dead connection was not detected"
    finally:
        client.stop_channels()


@pytest.mark.parametrize("ping_timeout", [None, 5])
def test_ping_timeout_disabled_or_not_below_interval_keeps_the_connection(ws_server, ping_timeout):
    # Disabled, or not smaller than the interval (which websocket-client
    # rejects): no pong check, and the listener thread keeps running.
    client = _open_client(ws_server, ping_interval=1, ping_timeout=ping_timeout)
    try:
        assert not _wait_until_lost(client, 2.5)
        assert client.connection_thread.is_alive()
    finally:
        client.stop_channels()
