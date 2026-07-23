# Copyright (c) 2023-2024 Datalayer, Inc.
#
# BSD 3-Clause License

"""Google Colab kernel client.

This module provides :class:`ColabKernelClient`, a thin specialization of
:class:`~jupyter_kernel_client.client.KernelClient` that knows how to connect to
a Google Colab runtime.

A Colab runtime is reached through a per-session proxy. Compared to a vanilla
Jupyter Server connection, it requires:

* a ``colab-runtime-proxy-token`` query parameter on the websocket URL, and
* the ``X-Colab-Client-Agent`` / ``X-Colab-Runtime-Proxy-Token`` HTTP headers on
  both the REST and websocket requests.

The ``server_url``, ``kernel_id`` and proxy token are typically obtained from a
Colab runtime assignment API.

Example:
    >>> from jupyter_kernel_client import ColabKernelClient
    >>> with ColabKernelClient(
    ...     server_url="https://....sandbox.colab.dev",
    ...     kernel_id="fd343487-3cb8-4573-8677-8beecc39585d",
    ...     proxy_token="...",
    ... ) as kernel:
    ...     reply = kernel.execute("print('hey')")
    ...     print(reply)
"""

from __future__ import annotations

import logging
import typing as t

from jupyter_kernel_client.client import KernelClient
from jupyter_kernel_client.wsclient import JupyterSubprotocol

#: HTTP header identifying the client agent to the Colab proxy.
COLAB_CLIENT_AGENT_HEADER = "X-Colab-Client-Agent"
#: HTTP header carrying the Colab runtime proxy token.
COLAB_RUNTIME_PROXY_TOKEN_HEADER = "X-Colab-Runtime-Proxy-Token"
#: Websocket query parameter carrying the Colab runtime proxy token.
COLAB_RUNTIME_PROXY_TOKEN_PARAM = "colab-runtime-proxy-token"
#: Default value advertised through :data:`COLAB_CLIENT_AGENT_HEADER`.
DEFAULT_COLAB_CLIENT_AGENT = "jupyter-kernel-client"


class ColabKernelClient(KernelClient):
    """Kernel client connected to a Google Colab runtime.

    Args:
        server_url: The Colab runtime proxy URL (from the assignment API).
        kernel_id: The identifier of the Colab kernel to connect to.
        proxy_token: The Colab runtime proxy token (from the assignment API).
        client_agent: Value sent through the ``X-Colab-Client-Agent`` header.
        subprotocol: Websocket subprotocol to use; Colab uses the default one.
        log: Optional logger.
        **kwargs: Forwarded to :class:`~jupyter_kernel_client.client.KernelClient`.
            ``client_kwargs`` and ``headers`` may be provided and are merged with
            the Colab-specific values.
    """

    def __init__(
        self,
        server_url: str,
        kernel_id: str,
        proxy_token: str,
        *,
        client_agent: str = DEFAULT_COLAB_CLIENT_AGENT,
        subprotocol: JupyterSubprotocol | None = JupyterSubprotocol.DEFAULT,
        log: logging.Logger | None = None,
        **kwargs: t.Any,
    ) -> None:
        client_kwargs: dict[str, t.Any] = dict(kwargs.pop("client_kwargs", None) or {})
        client_kwargs.setdefault("subprotocol", subprotocol)

        extra_params: dict[str, t.Any] = dict(client_kwargs.get("extra_params", None) or {})
        extra_params[COLAB_RUNTIME_PROXY_TOKEN_PARAM] = proxy_token
        client_kwargs["extra_params"] = extra_params

        headers: dict[str, t.Any] = dict(kwargs.pop("headers", None) or {})
        headers.setdefault(COLAB_CLIENT_AGENT_HEADER, client_agent)
        headers[COLAB_RUNTIME_PROXY_TOKEN_HEADER] = proxy_token

        # Colab authenticates through the proxy token, not the Jupyter token.
        # Drop any provided Jupyter token to avoid sending an Authorization
        # header and a `token=` query parameter that Colab does not use.
        kwargs.pop("token", None)

        super().__init__(
            kernel_id=kernel_id,
            log=log,
            server_url=server_url,
            token=None,
            client_kwargs=client_kwargs,
            headers=headers,
            **kwargs,
        )
