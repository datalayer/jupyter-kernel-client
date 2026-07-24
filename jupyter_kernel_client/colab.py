# Copyright (c) 2023-2024 Datalayer, Inc.
#
# BSD 3-Clause License

"""Google Colab kernel client.

This module provides :class:`ColabKernelClient`, a thin specialization of
:class:`~jupyter_kernel_client.client.KernelClient` that connects to an
**already-running** Google Colab kernel.

A Colab runtime is reached through a per-session proxy. Compared to a vanilla
Jupyter Server connection, it requires:

* a ``colab-runtime-proxy-token`` query parameter on the websocket URL, and
* the ``X-Colab-Client-Agent`` / ``X-Colab-Runtime-Proxy-Token`` HTTP headers on
  both the REST and websocket requests.

.. note::
   This client **reuses an existing kernel**; it does not create a Colab runtime
   from scratch. Consumer Colab has no public API to provision a runtime from a
   standalone process (authentication lives in the browser session). Start a
   runtime from the Colab UI, then connect to it here using the values taken
   from the websocket *channels* URL.

The ``server_url``, ``kernel_id`` and ``proxy_token`` are the parts of the
websocket *channels* URL that Colab's own frontend uses to reach your assigned
runtime, for example::

    wss://<host>/api/kernels/<kernel_id>/channels?session_id=<...>&colab-runtime-proxy-token=<proxy_token>&colab-client-agent=web

Use :func:`parse_colab_channels_url` (or
:meth:`ColabKernelClient.from_channels_url`) to turn that URL into the
``server_url``, ``kernel_id`` and ``proxy_token`` expected by the client.

Example:
    >>> from jupyter_kernel_client import ColabKernelClient
    >>> kernel = ColabKernelClient(
    ...     server_url="https://<colab-host>",
    ...     kernel_id="<kernel_id>",
    ...     proxy_token="<proxy_token>",
    ... )
    >>> kernel.start()
    >>> reply = kernel.execute("print('hey')")
    >>> print(reply)
    >>> kernel.stop(shutdown_kernel=False)  # disconnect only
"""

from __future__ import annotations

import logging
import re
import typing as t
from urllib.parse import parse_qs, urlsplit

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

#: Regular expression extracting the kernel id from a Colab channels URL.
_COLAB_KERNEL_RE = re.compile(r"/api/kernels/([^/]+)/channels", re.IGNORECASE)


def parse_colab_channels_url(channels_url: str) -> tuple[str, str, str]:
    """Extract ``server_url``, ``kernel_id`` and ``proxy_token`` from a URL.

    Parses the websocket *channels* URL of a running Colab kernel session, as
    seen in the browser network tab.

    Args:
        channels_url: The websocket *channels* URL of a running Colab kernel
            session, e.g.
            ``wss://<host>/api/kernels/<id>/channels?...&colab-runtime-proxy-token=<token>``.

    Returns:
        A ``(server_url, kernel_id, proxy_token)`` tuple where ``server_url`` is
        the HTTP(S) base *before* ``/api/kernels``, ``kernel_id`` is the kernel
        identifier, and ``proxy_token`` is the Colab runtime proxy token.

    Raises:
        ValueError: If the URL does not look like a Colab channels URL or is
            missing the proxy token.
    """
    split = urlsplit(channels_url)
    if not split.netloc:
        raise ValueError(
            f"Could not parse a Colab channels URL from: {channels_url!r}. "
            "Expected a websocket URL of the form "
            "'wss://<host>/api/kernels/<id>/channels?...&colab-runtime-proxy-token=<token>'."
        )

    scheme = "https" if split.scheme.lower() in ("wss", "https") else "http"

    marker = "/api/kernels/"
    idx = split.path.find(marker)
    if idx == -1:
        raise ValueError(
            f"Could not find '/api/kernels/' in: {channels_url!r}. "
            "Expected the URL to contain 'api/kernels/<id>/channels'."
        )
    prefix = split.path[:idx]
    server_url = f"{scheme}://{split.netloc}{prefix}"

    kernel_match = _COLAB_KERNEL_RE.search(split.path)
    if kernel_match is None:
        raise ValueError(
            f"Could not parse a Colab kernel id from: {channels_url!r}. "
            "Expected the URL to contain 'api/kernels/<id>/channels'."
        )
    kernel_id = kernel_match.group(1)

    query = parse_qs(split.query)
    proxy_tokens = query.get(COLAB_RUNTIME_PROXY_TOKEN_PARAM)
    if not proxy_tokens or not proxy_tokens[0]:
        raise ValueError(
            f"Could not find the '{COLAB_RUNTIME_PROXY_TOKEN_PARAM}' query "
            f"parameter in: {channels_url!r}."
        )
    proxy_token = proxy_tokens[0]

    return server_url, kernel_id, proxy_token


class ColabKernelClient(KernelClient):
    """Kernel client connected to an existing Google Colab runtime.

    This client connects to a kernel that is **already running** on a Colab
    runtime. It does not create a runtime from scratch.

    Args:
        server_url: The Colab runtime proxy URL (the HTTP(S) base *before*
            ``/api/kernels``, derived from the session's channels URL).
        proxy_token: The Colab runtime proxy token (the
            ``colab-runtime-proxy-token`` value from the channels URL).
        kernel_id: The identifier of the existing Colab kernel to connect to.
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
        proxy_token: str,
        *,
        kernel_id: str,
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

    @classmethod
    def from_channels_url(
        cls,
        channels_url: str,
        **kwargs: t.Any,
    ) -> ColabKernelClient:
        """Create a client from a Colab kernel session *channels* URL.

        Args:
            channels_url: The websocket *channels* URL of a running Colab kernel
                session (see :func:`parse_colab_channels_url`).
            **kwargs: Forwarded to :class:`ColabKernelClient`. Values provided
                here override those parsed from the URL.

        Returns:
            A configured :class:`ColabKernelClient` instance.
        """
        server_url, kernel_id, proxy_token = parse_colab_channels_url(channels_url)
        kwargs.setdefault("kernel_id", kernel_id)
        kwargs.setdefault("proxy_token", proxy_token)
        return cls(server_url=server_url, **kwargs)
