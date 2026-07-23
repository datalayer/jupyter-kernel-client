# Copyright (c) 2023-2024 Datalayer, Inc.
#
# BSD 3-Clause License

from __future__ import annotations

import json

import pytest
import websockets

from jupyter_kernel_client.browser_bridge import (
    BrowserBridgeError,
    BrowserBridgeServer,
    BrowserBridgeTimeout,
    ColabBridge,
    ColabConnectionInfo,
)


def _ws_url(bridge: BrowserBridgeServer, *, token: str | None = None) -> str:
    tok = bridge.token if token is None else token
    return f"ws://{bridge.host}:{bridge.port}/?access_token={tok}"


async def test_bridge_receives_first_json_payload():
    async with BrowserBridgeServer(open_browser=False) as bridge:
        async with websockets.connect(_ws_url(bridge)) as ws:
            await ws.send(json.dumps({"server_url": "https://host", "proxy_token": "tok"}))
            ack = await ws.recv()
        payload = await bridge.receive(timeout=5)

    assert payload == {"server_url": "https://host", "proxy_token": "tok"}
    assert json.loads(ack) == {"ok": True}


async def test_bridge_rejects_wrong_token():
    async with BrowserBridgeServer(open_browser=False) as bridge:
        with pytest.raises(websockets.exceptions.InvalidStatus):
            async with websockets.connect(_ws_url(bridge, token="nope")):
                pass


async def test_bridge_accepts_bearer_header():
    async with BrowserBridgeServer(open_browser=False, auth_query_param="") as bridge:
        url = f"ws://{bridge.host}:{bridge.port}/"
        headers = {"Authorization": f"Bearer {bridge.token}"}
        async with websockets.connect(url, additional_headers=headers) as ws:
            await ws.send(json.dumps({"hello": "world"}))
            await ws.recv()
        payload = await bridge.receive(timeout=5)

    assert payload == {"hello": "world"}


async def test_bridge_times_out_without_connection():
    async with BrowserBridgeServer(open_browser=False) as bridge:
        with pytest.raises(BrowserBridgeTimeout):
            await bridge.receive(timeout=0.2)


def test_render_url_substitutes_token_and_port():
    bridge = BrowserBridgeServer(
        open_browser=False,
        launch_url="https://x.test/#t={token}&p={port}",
        port=1234,
    )
    assert bridge.render_url() == f"https://x.test/#t={bridge.token}&p=1234"


def test_render_url_accepts_callable():
    bridge = BrowserBridgeServer(
        open_browser=False,
        launch_url=lambda token, port: f"custom://{token}:{port}",
        port=7,
    )
    assert bridge.render_url() == f"custom://{bridge.token}:7"


def test_colab_connection_info_from_payload_aliases():
    info = ColabConnectionInfo.from_payload(
        {
            "serverUrl": "https://colab-host",
            "colab-runtime-proxy-token": "proxy-abc",
            "kernelId": "kernel-123",
            "clientAgent": "my-agent",
            "extraField": "keep-me",
        }
    )
    assert info.server_url == "https://colab-host"
    assert info.proxy_token == "proxy-abc"
    assert info.kernel_id == "kernel-123"
    assert info.client_agent == "my-agent"
    assert info.extra == {"extraField": "keep-me"}


def test_colab_connection_info_requires_server_and_token():
    with pytest.raises(BrowserBridgeError):
        ColabConnectionInfo.from_payload({"server_url": "https://only-host"})


def test_colab_connection_info_to_kernel_client(monkeypatch):
    captured: dict = {}

    def fake_init(self, *args, **kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(
        "jupyter_kernel_client.colab.ColabKernelClient.__init__", fake_init
    )

    info = ColabConnectionInfo(
        server_url="https://colab-host",
        proxy_token="proxy-abc",
        kernel_id="kernel-123",
        client_agent="my-agent",
    )
    info.to_kernel_client()

    assert captured["server_url"] == "https://colab-host"
    assert captured["proxy_token"] == "proxy-abc"
    assert captured["kernel_id"] == "kernel-123"
    assert captured["client_agent"] == "my-agent"


def test_colab_bridge_defaults():
    bridge = ColabBridge(open_browser=False)
    assert bridge._allowed_origins == list(
        ("https://colab.research.google.com", "https://colab.google.com")
    )
    url = bridge.render_url()
    assert "bridgeToken=" in url and "bridgePort=" in url


async def test_colab_bridge_receive_connection():
    async with ColabBridge(open_browser=False, allowed_origins=None) as bridge:
        async with websockets.connect(_ws_url(bridge)) as ws:
            await ws.send(
                json.dumps({"server_url": "https://colab-host", "proxy_token": "tok"})
            )
            await ws.recv()
        info = await bridge.receive_connection(timeout=5)

    assert isinstance(info, ColabConnectionInfo)
    assert info.server_url == "https://colab-host"
    assert info.proxy_token == "tok"
