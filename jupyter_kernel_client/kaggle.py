# Copyright (c) 2023-2024 Datalayer, Inc.
#
# BSD 3-Clause License

"""Kaggle kernel client.

This module provides :class:`KaggleKernelClient`, a thin specialization of
:class:`~jupyter_kernel_client.client.KernelClient` that knows how to connect to
a Kaggle interactive notebook runtime.

There are two ways to authenticate:

* **API token (default).** Provide a Kaggle API token, either explicitly through
  the ``token`` argument or via the :data:`KAGGLE_API_TOKEN` environment
  variable. The token is used to authenticate REST/websocket requests, so
  omitting ``kernel_id`` lets :meth:`start` *create* a new kernel on the runtime
  (``POST /api/kernels``).
* **Signed proxy URL.** When you connect to an already-running notebook session,
  the signed JWT embedded in the proxied ``server_url`` path carries the
  authentication and no token is required (pass ``token=None`` explicitly).

The ``server_url`` and ``kernel_id`` can be derived from the websocket
*channels* URL of a running Kaggle notebook session (visible in the browser
network tab), for example::

    wss://kkb-production.jupyter-proxy.kaggle.net/k/12345678/eyJhbGci.../proxy/api/kernels/11e073f0-e82d-4029-be8d-3918f7ed1a9e/channels?session_id=...

Use :func:`parse_kaggle_channels_url` (or
:meth:`KaggleKernelClient.from_channels_url`) to turn that URL into the
``server_url`` and ``kernel_id`` expected by the client.

Example:
    >>> import os
    >>> from jupyter_kernel_client import KaggleKernelClient
    >>> os.environ["KAGGLE_API_TOKEN"] = "..."
    >>> with KaggleKernelClient(server_url="https://.../proxy") as kernel:
    ...     print("kernel_id:", kernel.id)  # a new kernel was created
    ...     reply = kernel.execute("print('hey')")
    ...     print(reply)
"""

from __future__ import annotations

import logging
import os
import re
import typing as t

from jupyter_kernel_client.client import KernelClient
from jupyter_kernel_client.wsclient import JupyterSubprotocol

#: Environment variable holding the Kaggle API token used for authentication.
KAGGLE_API_TOKEN_ENV = "KAGGLE_API_TOKEN"  # noqa: S105
_TOKEN_UNSET = object()
#: Regular expression matching the proxied server base of a Kaggle channels URL.
_KAGGLE_SERVER_RE = re.compile(r"^(wss?)://(.*?)/proxy", re.IGNORECASE)
#: Regular expression extracting the kernel id from a Kaggle channels URL.
_KAGGLE_KERNEL_RE = re.compile(r"kernels/([0-9a-f-]+)/channels", re.IGNORECASE)


def parse_kaggle_channels_url(channels_url: str) -> tuple[str, str]:
    """Extract the ``server_url`` and ``kernel_id`` from a Kaggle channels URL.

    Args:
        channels_url: The websocket *channels* URL of a running Kaggle notebook
            session, e.g. ``wss://.../proxy/api/kernels/<id>/channels?...``.

    Returns:
        A ``(server_url, kernel_id)`` tuple where ``server_url`` is the HTTP(S)
        base ending in ``/proxy`` and ``kernel_id`` is the kernel identifier.

    Raises:
        ValueError: If the URL does not look like a Kaggle channels URL.
    """
    server_match = _KAGGLE_SERVER_RE.match(channels_url)
    if server_match is None:
        raise ValueError(
            f"Could not parse a Kaggle proxy server URL from: {channels_url!r}. "
            "Expected a websocket URL of the form 'wss://.../proxy/api/kernels/<id>/channels'."
        )
    scheme = "https" if server_match.group(1).lower() == "wss" else "http"
    server_url = f"{scheme}://{server_match.group(2)}/proxy"

    kernel_match = _KAGGLE_KERNEL_RE.search(channels_url)
    if kernel_match is None:
        raise ValueError(
            f"Could not parse a Kaggle kernel id from: {channels_url!r}. "
            "Expected the URL to contain 'kernels/<id>/channels'."
        )
    kernel_id = kernel_match.group(1)

    return server_url, kernel_id


class KaggleKernelClient(KernelClient):
    """Kernel client connected to a Kaggle interactive notebook runtime.

    Args:
        server_url: The Kaggle runtime proxy URL (ending in ``/proxy``). This is
            the HTTP(S) base derived from the notebook session's channels URL.
        kernel_id: The identifier of the Kaggle kernel to connect to. If omitted,
            :meth:`start` creates a new kernel on the runtime (which requires a
            valid API ``token``).
        token: The Kaggle API token used to authenticate. When omitted, it
            falls back to the :data:`KAGGLE_API_TOKEN` environment variable.
            Pass ``token=None`` to rely solely on the signed proxy
            ``server_url`` (even if the environment variable is set).
        subprotocol: Websocket subprotocol to use; Kaggle uses the default one.
        log: Optional logger.
        **kwargs: Forwarded to :class:`~jupyter_kernel_client.client.KernelClient`.
            ``client_kwargs`` may be provided and is merged with the
            Kaggle-specific values.
    """

    def __init__(
        self,
        server_url: str,
        *,
        kernel_id: str | None = None,
        token: str | None | object = _TOKEN_UNSET,
        subprotocol: JupyterSubprotocol | None = JupyterSubprotocol.DEFAULT,
        log: logging.Logger | None = None,
        **kwargs: t.Any,
    ) -> None:
        client_kwargs: dict[str, t.Any] = dict(kwargs.pop("client_kwargs", None) or {})
        client_kwargs.setdefault("subprotocol", subprotocol)

        # Resolve the Kaggle API token from the environment only when omitted.
        # Explicit ``token=None`` disables env fallback and relies on signed
        # proxy authentication embedded in ``server_url``.
        if token is _TOKEN_UNSET:
            token = os.environ.get(KAGGLE_API_TOKEN_ENV)

        super().__init__(
            kernel_id=kernel_id,
            log=log,
            server_url=server_url,
            token=token,
            client_kwargs=client_kwargs,
            **kwargs,
        )

    @classmethod
    def from_channels_url(
        cls,
        channels_url: str,
        **kwargs: t.Any,
    ) -> KaggleKernelClient:
        """Create a client from a Kaggle notebook session *channels* URL.

        Args:
            channels_url: The websocket *channels* URL of a running Kaggle
                notebook session (see :func:`parse_kaggle_channels_url`).
            **kwargs: Forwarded to :class:`KaggleKernelClient`. A ``kernel_id``
                provided here overrides the one parsed from the URL.

        Returns:
            A configured :class:`KaggleKernelClient` instance.
        """
        server_url, kernel_id = parse_kaggle_channels_url(channels_url)
        kwargs.setdefault("kernel_id", kernel_id)
        return cls(server_url=server_url, **kwargs)
