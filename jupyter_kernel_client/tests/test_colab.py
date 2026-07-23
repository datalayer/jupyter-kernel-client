# Copyright (c) 2023-2024 Datalayer, Inc.
#
# BSD 3-Clause License

from __future__ import annotations

import logging

from jupyter_kernel_client.colab import (
    COLAB_CLIENT_AGENT_HEADER,
    COLAB_RUNTIME_PROXY_TOKEN_HEADER,
    COLAB_RUNTIME_PROXY_TOKEN_PARAM,
    ColabKernelClient,
)


def test_colab_kernel_client_injects_headers_and_extra_params(monkeypatch):
    captured: dict = {}

    def fake_kernel_client_init(self, *args, **kwargs):
        captured.update(kwargs)

    monkeypatch.setattr("jupyter_kernel_client.colab.KernelClient.__init__", fake_kernel_client_init)

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

    monkeypatch.setattr("jupyter_kernel_client.colab.KernelClient.__init__", fake_kernel_client_init)

    ColabKernelClient(
        server_url="https://colab-host.example",
        kernel_id="kernel-123",
        proxy_token="proxy-abc",
        token="should-be-ignored",
        log=logging.getLogger("test"),
    )

    assert captured["token"] is None
