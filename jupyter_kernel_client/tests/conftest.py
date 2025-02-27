# Copyright (c) 2023-2024 Datalayer, Inc.
#
# BSD 3-Clause License

import io
import logging
import secrets
import signal
import socket
import typing as t
from contextlib import closing
from pathlib import Path
from subprocess import PIPE, Popen, TimeoutExpired

import pytest
import requests

logging.basicConfig(level=logging.DEBUG)
logging.getLogger("urllib3.connectionpool").setLevel(logging.WARNING)


def find_free_port():
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("localhost", 0))
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return s.getsockname()[1]


def print_stream(stream):
    for line in stream.split(b"\n"):
        print(line.decode())


@pytest.fixture
def jupyter_server(tmp_path: Path) -> t.Generator[tuple[str, str], t.Any, t.Any]:
    port = find_free_port()
    token = secrets.token_hex(20)

    stdout = tmp_path / "stdout.log"
    stderr = tmp_path / "stderr.log"

    with stdout.open("wb") as out, stderr.open("wb") as err:
        jp_server = Popen(
            [
                "jupyter-server",
                "--port",
                str(port),
                "--IdentityProvider.token",
                token,
                "--debug",
                "--ServerApp.open_browser",
                "False",
            ],
            stdout=out,
            stderr=err,
        )

        starting = True
        while starting:
            try:
                ans = requests.get(f"http://localhost:{port}/api", timeout=1)
                if ans.status_code == 200:
                    logging.debug("Server ready at http://localhost:%s", port)
                    break
            except requests.RequestException:
                ...
        try:
            yield (str(port), token)
        finally:
            jp_server.send_signal(signal.SIGINT)
            jp_server.send_signal(signal.SIGINT)
            try:
                jp_server.communicate(timeout=5)
            except TimeoutExpired:
                if jp_server.poll() is None:
                    jp_server.terminate()
    try:
        print_stream(out.read())
    except io.UnsupportedOperation:
        ...
    try:
        print_stream(err.read())
    except io.UnsupportedOperation:
        ...
