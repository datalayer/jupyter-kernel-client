# Copyright (c) 2023-2024 Datalayer, Inc.
#
# BSD 3-Clause License

"""Generic browser bridge for handing connection details to a local process.

Some services (most notably consumer Google Colab) cannot be provisioned from a
standalone process with an API key: authentication lives in the user's browser
session. Google's own ``colab-mcp`` works around this with a *browser bridge*:

1. A local WebSocket server is started on ``localhost`` with a freshly generated
   shared token and an ``Origin`` allowlist.
2. A browser page (already authenticated to the target service) is opened with
   the token and port embedded in the URL.
3. The authenticated page connects back to the local server and delivers a
   payload (for Colab, the runtime ``server_url`` / ``kernel_id`` /
   ``proxy_token``). Google's credentials never leave the browser.

This module provides that bridge as a small, reusable, transport-agnostic
primitive so it can be shared by ``jupyter-kernel-client``, ``code-sandboxes``
and ``jupyter-mcp-server``.

:class:`BrowserBridgeServer` is fully generic (configurable host, port, token,
origins, subprotocols, launch URL and auth parameter). :class:`ColabBridge` and
:func:`request_colab_connection` are thin Colab-flavored presets that turn the
received payload into a :class:`~jupyter_kernel_client.colab.ColabKernelClient`.

.. note::
   Vanilla Colab will not spontaneously post back to this bridge. The browser
   side must run a cooperating page, extension or userscript that reads the
   ``token``/``port`` from the launch URL and sends the JSON payload described in
   :meth:`ColabConnectionInfo.from_payload`. This module implements the *local*
   half of that handshake; it does not fabricate an unofficial Colab API.

Example (generic)::

    from jupyter_kernel_client import request_payload

    payload = request_payload(
        launch_url="https://example.test/bridge#token={token}&port={port}",
        allowed_origins=["https://example.test"],
    )

Example (Colab)::

    from jupyter_kernel_client import request_colab_connection

    info = request_colab_connection()
    with info.to_kernel_client() as kernel:
        print(kernel.execute("print(1 + 1)"))
"""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
import typing as t
from dataclasses import dataclass, field

from jupyter_kernel_client.log import get_logger

try:  # pragma: no cover - exercised indirectly through the guard below
    import websockets
    from websockets.asyncio.server import ServerConnection
    from websockets.datastructures import Headers
    from websockets.http11 import Request, Response
    from websockets.typing import Subprotocol

    _HAS_WEBSOCKETS = True
    _WEBSOCKETS_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover - depends on optional dependency
    _HAS_WEBSOCKETS = False
    _WEBSOCKETS_IMPORT_ERROR = exc

#: Default host the bridge binds to. Loopback only for safety.
DEFAULT_BRIDGE_HOST = "localhost"
#: Default query-string parameter used to carry the shared token.
DEFAULT_AUTH_QUERY_PARAM = "access_token"
#: Default number of seconds to wait for the browser to deliver a payload.
DEFAULT_CONNECTION_TIMEOUT = 60.0

#: Origins from which a Colab browser session may connect back.
COLAB_ORIGINS: tuple[str, ...] = (
    "https://colab.research.google.com",
    "https://colab.google.com",
)
#: Default Colab page opened to trigger the bridge handshake.
DEFAULT_COLAB_LAUNCH_URL = (
    "https://colab.research.google.com/notebooks/empty.ipynb"
    "#bridgeToken={token}&bridgePort={port}"
)

LaunchURL = t.Union[str, t.Callable[[str, int], str]]


class BrowserBridgeError(RuntimeError):
    """Base error for :mod:`jupyter_kernel_client.browser_bridge`."""


class BrowserBridgeTimeout(BrowserBridgeError):
    """Raised when the browser does not connect back in time."""


def _require_websockets() -> None:
    if not _HAS_WEBSOCKETS:
        raise BrowserBridgeError(
            "The 'websockets' package is required for the browser bridge. "
            "Install it with: pip install jupyter-kernel-client[bridge]"
        ) from _WEBSOCKETS_IMPORT_ERROR


class BrowserBridgeServer:
    """Localhost WebSocket bridge that receives a payload from a browser page.

    The server accepts a single authenticated connection, reads the first JSON
    object the browser sends, and exposes it through :meth:`receive`.

    Args:
        launch_url: URL opened in the browser. Either a template string with
            ``{token}`` and ``{port}`` placeholders, or a callable
            ``(token, port) -> url``. Optional when the browser is opened by the
            caller (set ``open_browser=False``).
        host: Interface to bind to. Defaults to ``localhost`` (loopback only).
        port: Port to bind to. ``0`` (default) picks a free port.
        token: Shared secret required to connect. Generated when omitted.
        allowed_origins: Iterable of allowed ``Origin`` header values. ``None``
            (default) disables origin checking (useful for tests and non-browser
            callers); pass an explicit list in production.
        subprotocols: WebSocket subprotocols to advertise. ``None`` for plain.
        auth_query_param: Query-string parameter matched against ``token``
            (in addition to an ``Authorization: Bearer <token>`` header).
        open_browser: Whether to open ``launch_url`` automatically on start.
        connection_timeout: Default seconds :meth:`receive` waits.
        log: Optional logger.
    """

    def __init__(
        self,
        *,
        launch_url: LaunchURL | None = None,
        host: str = DEFAULT_BRIDGE_HOST,
        port: int = 0,
        token: str | None = None,
        allowed_origins: t.Sequence[str] | None = None,
        subprotocols: t.Sequence[str] | None = None,
        auth_query_param: str = DEFAULT_AUTH_QUERY_PARAM,
        open_browser: bool = True,
        connection_timeout: float = DEFAULT_CONNECTION_TIMEOUT,
        log: logging.Logger | None = None,
    ) -> None:
        _require_websockets()
        self._launch_url = launch_url
        self.host = host
        self.port = port
        self.token = token or secrets.token_urlsafe(16)
        self._allowed_origins = list(allowed_origins) if allowed_origins is not None else None
        self._subprotocols = list(subprotocols) if subprotocols is not None else None
        self._auth_query_param = auth_query_param
        self._open_browser = open_browser
        self._connection_timeout = connection_timeout
        self.log = log or get_logger()

        self._server: t.Any = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._payload_future: asyncio.Future[dict[str, t.Any]] | None = None
        self._connection_lock = asyncio.Lock()

    # -- URL -------------------------------------------------------------

    @property
    def url(self) -> str:
        """The rendered launch URL (with token and port substituted)."""
        return self.render_url()

    def render_url(self) -> str:
        """Render :paramref:`launch_url` with the current token and port."""
        if self._launch_url is None:
            raise BrowserBridgeError("No 'launch_url' was configured for this bridge.")
        if callable(self._launch_url):
            return self._launch_url(self.token, self.port)
        return self._launch_url.format(token=self.token, port=self.port)

    # -- Authorization ---------------------------------------------------

    def _validate_authorization(
        self, connection: "ServerConnection", request: "Request"
    ) -> "Response | None":
        # Accept the shared token either as a query parameter on the request
        # target or as an ``Authorization: Bearer <token>`` header.
        if (
            self._auth_query_param
            and f"{self._auth_query_param}={self.token}" in request.path
        ):
            return None
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            return Response(401, "Missing authorization", Headers([]))
        try:
            scheme, value = auth_header.split(None, 1)
        except ValueError:
            return Response(400, "Invalid authorization header", Headers([]))
        if scheme.lower() != "bearer":
            return Response(400, "Invalid authorization scheme", Headers([]))
        if secrets.compare_digest(value, self.token):
            return None
        return Response(403, "Bad authorization token", Headers([]))

    # -- Payload handling ------------------------------------------------

    @staticmethod
    def _parse_message(message: str | bytes) -> dict[str, t.Any] | None:
        if isinstance(message, bytes):
            try:
                message = message.decode("utf-8")
            except UnicodeDecodeError:
                return None
        try:
            parsed = json.loads(message)
        except (ValueError, TypeError):
            return None
        if isinstance(parsed, dict):
            return parsed
        return None

    async def _handler(self, websocket: "ServerConnection") -> None:
        if self._connection_lock.locked():
            await websocket.close(code=1013, reason="Bridge is busy")
            return
        async with self._connection_lock:
            try:
                async for message in websocket:
                    payload = self._parse_message(message)
                    if payload is None:
                        continue
                    if self._payload_future is not None and not self._payload_future.done():
                        self._payload_future.set_result(payload)
                    # Acknowledge and stop after the first valid payload.
                    try:
                        await websocket.send(json.dumps({"ok": True}))
                    except Exception:  # pragma: no cover - best-effort ack
                        pass
                    break
            except Exception as exc:  # pragma: no cover - transport errors
                self.log.debug("Browser bridge connection error: %s", exc)

    # -- Lifecycle -------------------------------------------------------

    async def __aenter__(self) -> "BrowserBridgeServer":
        self._loop = asyncio.get_running_loop()
        self._payload_future = self._loop.create_future()

        serve_kwargs: dict[str, t.Any] = {
            "host": self.host,
            "port": self.port,
            "process_request": self._validate_authorization,
        }
        if self._allowed_origins is not None:
            serve_kwargs["origins"] = self._allowed_origins
        if self._subprotocols is not None:
            serve_kwargs["subprotocols"] = [Subprotocol(s) for s in self._subprotocols]

        self._server = await websockets.serve(self._handler, **serve_kwargs)
        self.port = self._server.sockets[0].getsockname()[1]
        self.log.info("Browser bridge listening on ws://%s:%s", self.host, self.port)

        if self._open_browser and self._launch_url is not None:
            self.open()
        return self

    async def __aexit__(self, exc_type: t.Any, exc_val: t.Any, exc_tb: t.Any) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    def open(self) -> str:
        """Open the launch URL in the user's default browser and return it."""
        import webbrowser

        url = self.render_url()
        webbrowser.open_new(url)
        return url

    async def receive(self, timeout: float | None = None) -> dict[str, t.Any]:
        """Wait for and return the first JSON payload sent by the browser.

        Args:
            timeout: Seconds to wait. Defaults to ``connection_timeout``.

        Raises:
            BrowserBridgeTimeout: If no payload arrives in time.
        """
        if self._payload_future is None:
            raise BrowserBridgeError("The bridge server is not running.")
        wait = self._connection_timeout if timeout is None else timeout
        try:
            return await asyncio.wait_for(asyncio.shield(self._payload_future), timeout=wait)
        except asyncio.TimeoutError as exc:
            raise BrowserBridgeTimeout(
                f"No browser connection received within {wait:g}s."
            ) from exc


def request_payload(
    *,
    launch_url: LaunchURL | None = None,
    timeout: float = DEFAULT_CONNECTION_TIMEOUT,
    **kwargs: t.Any,
) -> dict[str, t.Any]:
    """Synchronously run a :class:`BrowserBridgeServer` and return one payload.

    Convenience wrapper for callers that are not already inside an event loop
    (e.g. CLIs). Accepts the same keyword arguments as
    :class:`BrowserBridgeServer`.
    """

    async def _run() -> dict[str, t.Any]:
        async with BrowserBridgeServer(launch_url=launch_url, **kwargs) as bridge:
            return await bridge.receive(timeout=timeout)

    return asyncio.run(_run())


@dataclass
class ColabConnectionInfo:
    """Colab runtime connection details delivered through the browser bridge."""

    server_url: str
    proxy_token: str
    kernel_id: str | None = None
    client_agent: str | None = None
    extra: dict[str, t.Any] = field(default_factory=dict)

    #: Accepted aliases for each field in the browser payload.
    _ALIASES: t.ClassVar[dict[str, tuple[str, ...]]] = {
        "server_url": ("server_url", "serverUrl", "url"),
        "proxy_token": ("proxy_token", "proxyToken", "colab-runtime-proxy-token"),
        "kernel_id": ("kernel_id", "kernelId"),
        "client_agent": ("client_agent", "clientAgent"),
    }

    @classmethod
    def from_payload(cls, payload: t.Mapping[str, t.Any]) -> "ColabConnectionInfo":
        """Build connection info from a browser payload.

        The payload is a JSON object with (case-insensitive alias) keys:

        * ``server_url`` (required) — Colab runtime proxy URL.
        * ``proxy_token`` (required) — Colab runtime proxy token.
        * ``kernel_id`` (optional) — existing kernel to attach to.
        * ``client_agent`` (optional) — value for ``X-Colab-Client-Agent``.

        Unrecognized keys are preserved on :attr:`extra`.
        """

        def _pick(field_name: str) -> t.Any:
            for alias in cls._ALIASES[field_name]:
                if alias in payload and payload[alias] is not None:
                    return payload[alias]
            return None

        server_url = _pick("server_url")
        proxy_token = _pick("proxy_token")
        if not server_url or not proxy_token:
            raise BrowserBridgeError(
                "Colab bridge payload must include 'server_url' and 'proxy_token'."
            )

        known = {alias for aliases in cls._ALIASES.values() for alias in aliases}
        extra = {k: v for k, v in payload.items() if k not in known}

        return cls(
            server_url=str(server_url),
            proxy_token=str(proxy_token),
            kernel_id=_pick("kernel_id"),
            client_agent=_pick("client_agent"),
            extra=extra,
        )

    def to_kernel_client(self, **kwargs: t.Any) -> t.Any:
        """Create a :class:`~jupyter_kernel_client.colab.ColabKernelClient`."""
        from jupyter_kernel_client.colab import ColabKernelClient

        if self.client_agent is not None:
            kwargs.setdefault("client_agent", self.client_agent)
        return ColabKernelClient(
            server_url=self.server_url,
            proxy_token=self.proxy_token,
            kernel_id=self.kernel_id,
            **kwargs,
        )


class ColabBridge(BrowserBridgeServer):
    """A :class:`BrowserBridgeServer` preset for Google Colab.

    Restricts origins to the Colab domains and opens a scratch Colab notebook
    with the bridge token and port in the URL fragment.
    """

    def __init__(
        self,
        *,
        launch_url: LaunchURL | None = DEFAULT_COLAB_LAUNCH_URL,
        allowed_origins: t.Sequence[str] | None = COLAB_ORIGINS,
        **kwargs: t.Any,
    ) -> None:
        super().__init__(
            launch_url=launch_url,
            allowed_origins=allowed_origins,
            **kwargs,
        )

    async def receive_connection(
        self, timeout: float | None = None
    ) -> ColabConnectionInfo:
        """Wait for the browser payload and parse it into connection info."""
        payload = await self.receive(timeout=timeout)
        return ColabConnectionInfo.from_payload(payload)


def request_colab_connection(
    *,
    timeout: float = DEFAULT_CONNECTION_TIMEOUT,
    **kwargs: t.Any,
) -> ColabConnectionInfo:
    """Synchronously obtain Colab connection info via the browser bridge.

    Opens a Colab page, waits for the authenticated browser session to deliver
    the runtime details, and returns a :class:`ColabConnectionInfo`. Accepts the
    same keyword arguments as :class:`ColabBridge`.
    """

    async def _run() -> ColabConnectionInfo:
        async with ColabBridge(**kwargs) as bridge:
            return await bridge.receive_connection(timeout=timeout)

    return asyncio.run(_run())
