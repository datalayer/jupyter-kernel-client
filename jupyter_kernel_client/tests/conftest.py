import logging
import secrets
import signal
import socket
import typing as t
from contextlib import closing
from subprocess import PIPE, Popen

import pytest
import requests

LOG = {b"C": logging.critical, b"W": logging.warning, b"I": logging.info, b"D": logging.debug}


def find_free_port():
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("localhost", 0))
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return s.getsockname()[1]


@pytest.fixture
def jupyter_server() -> t.Generator[tuple[str, str], t.Any, t.Any]:
    port = find_free_port()
    token = secrets.token_hex(20)

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
        stdout=PIPE,
        stderr=PIPE,
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
        out, err = jp_server.communicate()

        def print_stream(stream):
            for line in stream.split(b"\n"):
                if len(line) >= 2 and line[0] == b"[":
                    LOG.get(line[1], logging.debug)(line.decode())
                else:
                    logging.info(line.decode())

        print_stream(out)
        print_stream(err)
