# Copyright (c) 2023-2024 Datalayer, Inc.
#
# BSD 3-Clause License

from __future__ import annotations

import logging

import pytest

from jupyter_kernel_client.colab import (
    COLAB_CLIENT_AGENT_HEADER,
    COLAB_RUNTIME_PROXY_TOKEN_HEADER,
    COLAB_RUNTIME_PROXY_TOKEN_PARAM,
    ColabKernelClient,
    parse_colab_channels_url,
)

CHANNELS_URL = (
    "wss://abc123.prod.colab.dev/api/kernels/"
    "11e073f0-e82d-4029-be8d-3918f7ed1a9e/channels"
    "?session_id=96f4a03c-e4e0-4f15-8e9f-0cd33d3edecf"
    "&colab-runtime-proxy-token=proxy-abc"
    "&colab-client-agent=web"
)
SERVER_URL = "https://abc123.prod.colab.dev"
KERNEL_ID = "11e073f0-e82d-4029-be8d-3918f7ed1a9e"
PROXY_TOKEN = "proxy-abc"  # noqa: S105



def test_colab_kernel_client_injects_headers_and_extra_params(monkeypatch):
    captured: dict = {}

    def fake_kernel_client_init(self, *args, **kwargs):
        captured.update(kwargs)

    monkeypatch.setattr("jupyter_kernel_client.colab.JupyterKernelClient.__init__", fake_kernel_client_init)

    ColabKernelClient(
        server_url="https://colab-host.example",
        kernel_id="kernel-123",
        proxy_token="proxy-abc",
        client_agent="custom-agent",
        headers={"Existing": "value"},
        client_kwargs={"extra_params": {"existing": "p"}},
    )

    assert captured["server_url"] == "https://colab-host.example"
    assert captured["kernel_id"] == "kernel-123"
    assert captured["token"] is None

    headers = captured["headers"]
    assert headers["Existing"] == "value"
    assert headers[COLAB_CLIENT_AGENT_HEADER] == "custom-agent"
    assert headers[COLAB_RUNTIME_PROXY_TOKEN_HEADER] == "proxy-abc"

    client_kwargs = captured["client_kwargs"]
    assert client_kwargs["extra_params"]["existing"] == "p"
    assert client_kwargs["extra_params"][COLAB_RUNTIME_PROXY_TOKEN_PARAM] == "proxy-abc"


def test_colab_kernel_client_drops_any_provided_jupyter_token(monkeypatch):
    captured: dict = {}

    def fake_kernel_client_init(self, *args, **kwargs):
        captured.update(kwargs)

    monkeypatch.setattr("jupyter_kernel_client.colab.JupyterKernelClient.__init__", fake_kernel_client_init)

    ColabKernelClient(
        server_url="https://colab-host.example",
        kernel_id="kernel-123",
        proxy_token="proxy-abc",
        token="should-be-ignored",
        log=logging.getLogger("test"),
    )

    assert captured["token"] is None


def test_parse_colab_channels_url_extracts_parts():
    server_url, kernel_id, proxy_token = parse_colab_channels_url(CHANNELS_URL)
    assert server_url == SERVER_URL
    assert kernel_id == KERNEL_ID
    assert proxy_token == PROXY_TOKEN


def test_parse_colab_channels_url_maps_ws_to_http():
    server_url, _, _ = parse_colab_channels_url(CHANNELS_URL.replace("wss://", "ws://"))
    assert server_url.startswith("http://")


def test_parse_colab_channels_url_requires_proxy_token():
    without_token = CHANNELS_URL.replace("&colab-runtime-proxy-token=proxy-abc", "")
    with pytest.raises(ValueError):
        parse_colab_channels_url(without_token)


def test_parse_colab_channels_url_rejects_invalid_url():
    with pytest.raises(ValueError):
        parse_colab_channels_url("https://colab.research.google.com/not-a-channels-url")


def test_colab_kernel_client_from_channels_url(monkeypatch):
    captured: dict = {}

    def fake_kernel_client_init(self, *args, **kwargs):
        captured.update(kwargs)

    monkeypatch.setattr("jupyter_kernel_client.colab.JupyterKernelClient.__init__", fake_kernel_client_init)

    ColabKernelClient.from_channels_url(CHANNELS_URL)

    assert captured["server_url"] == SERVER_URL
    assert captured["kernel_id"] == KERNEL_ID
    headers = captured["headers"]
    assert headers[COLAB_RUNTIME_PROXY_TOKEN_HEADER] == PROXY_TOKEN
    client_kwargs = captured["client_kwargs"]
    assert client_kwargs["extra_params"][COLAB_RUNTIME_PROXY_TOKEN_PARAM] == PROXY_TOKEN

