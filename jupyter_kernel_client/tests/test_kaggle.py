# Copyright (c) 2023-2024 Datalayer, Inc.
#
# BSD 3-Clause License

from __future__ import annotations

import logging

import pytest

from jupyter_kernel_client.kaggle import (
    KaggleKernelClient,
    parse_kaggle_channels_url,
)

CHANNELS_URL = (
    "wss://kkb-production.jupyter-proxy.kaggle.net/k/12345678/eyJhbGciMGIgwPdMJ"
    "/proxy/api/kernels/11e073f0-e82d-4029-be8d-3918f7ed1a9e/channels"
    "?session_id=96f4a03c-e4e0-4f15-8e9f-0cd33d3edecf"
)
SERVER_URL = "https://kkb-production.jupyter-proxy.kaggle.net/k/12345678/eyJhbGciMGIgwPdMJ/proxy"
KERNEL_ID = "11e073f0-e82d-4029-be8d-3918f7ed1a9e"


def test_parse_kaggle_channels_url_extracts_server_and_kernel():
    server_url, kernel_id = parse_kaggle_channels_url(CHANNELS_URL)
    assert server_url == SERVER_URL
    assert kernel_id == KERNEL_ID


def test_parse_kaggle_channels_url_maps_ws_to_http():
    server_url, _ = parse_kaggle_channels_url(CHANNELS_URL.replace("wss://", "ws://"))
    assert server_url.startswith("http://")


def test_parse_kaggle_channels_url_rejects_invalid_url():
    with pytest.raises(ValueError):
        parse_kaggle_channels_url("https://kaggle.com/not-a-channels-url")


def test_kaggle_kernel_client_uses_explicit_token(monkeypatch):
    captured: dict = {}

    def fake_kernel_client_init(self, *args, **kwargs):
        captured.update(kwargs)

    monkeypatch.delenv("KAGGLE_API_TOKEN", raising=False)
    monkeypatch.setattr(
        "jupyter_kernel_client.kaggle.KernelClient.__init__", fake_kernel_client_init
    )

    KaggleKernelClient(
        server_url=SERVER_URL,
        kernel_id=KERNEL_ID,
        token="explicit-token",  # noqa: S106
        log=logging.getLogger("test"),
    )

    assert captured["server_url"] == SERVER_URL
    assert captured["kernel_id"] == KERNEL_ID
    assert captured["token"] == "explicit-token"  # noqa: S105


def test_kaggle_kernel_client_reads_token_from_env(monkeypatch):
    captured: dict = {}

    def fake_kernel_client_init(self, *args, **kwargs):
        captured.update(kwargs)

    monkeypatch.setenv("KAGGLE_API_TOKEN", "env-token")
    monkeypatch.setattr(
        "jupyter_kernel_client.kaggle.KernelClient.__init__", fake_kernel_client_init
    )

    KaggleKernelClient(server_url=SERVER_URL)

    assert captured["token"] == "env-token"  # noqa: S105


def test_kaggle_kernel_client_token_none_without_env(monkeypatch):
    captured: dict = {}

    def fake_kernel_client_init(self, *args, **kwargs):
        captured.update(kwargs)

    monkeypatch.delenv("KAGGLE_API_TOKEN", raising=False)
    monkeypatch.setattr(
        "jupyter_kernel_client.kaggle.KernelClient.__init__", fake_kernel_client_init
    )

    KaggleKernelClient(server_url=SERVER_URL)

    assert captured["token"] is None


def test_kaggle_kernel_client_from_channels_url(monkeypatch):
    captured: dict = {}

    def fake_kernel_client_init(self, *args, **kwargs):
        captured.update(kwargs)

    monkeypatch.delenv("KAGGLE_API_TOKEN", raising=False)
    monkeypatch.setattr(
        "jupyter_kernel_client.kaggle.KernelClient.__init__", fake_kernel_client_init
    )

    KaggleKernelClient.from_channels_url(CHANNELS_URL)

    assert captured["server_url"] == SERVER_URL
    assert captured["kernel_id"] == KERNEL_ID


def test_kaggle_kernel_client_allows_missing_kernel_id_for_new_kernel(monkeypatch):
    captured: dict = {}

    def fake_kernel_client_init(self, *args, **kwargs):
        captured.update(kwargs)

    monkeypatch.setenv("KAGGLE_API_TOKEN", "env-token")
    monkeypatch.setattr(
        "jupyter_kernel_client.kaggle.KernelClient.__init__", fake_kernel_client_init
    )

    KaggleKernelClient(server_url=SERVER_URL)

    assert captured["kernel_id"] is None
    assert captured["token"] == "env-token"  # noqa: S105
