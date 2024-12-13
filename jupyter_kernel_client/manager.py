# Copyright (c) 2023-2024 Datalayer, Inc.
#
# BSD 3-Clause License

from __future__ import annotations

import datetime
import os
import re
import typing as t
from time import sleep

import requests
from requests.exceptions import HTTPError
from traitlets import DottedObjectName, Type, default, observe
from traitlets.config import LoggingConfigurable
from traitlets.utils.importstring import import_item

from .constants import REQUEST_TIMEOUT
from .utils import url_path_join, utcnow

HTTP_PROTOCOL_REGEXP = re.compile(r"^http")


def fetch(
    request: str,
    token: str | None = None,
    **kwargs: t.Any,
) -> requests.Response:
    """Fetch a network resource as a context manager."""
    method = kwargs.pop("method", "GET")
    f = getattr(requests, method.lower())
    headers = kwargs.pop("headers", {})
    if len(headers) == 0:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "Jupyter kernels CLI",
        }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if "timeout" not in kwargs:
        kwargs["timeout"] = REQUEST_TIMEOUT
    response = f(request, headers=headers, **kwargs)
    response.raise_for_status()
    return response


class KernelHttpManager(LoggingConfigurable):
    """Manages a single remote kernel.

    Arguments
    ---------
    server_url : str
        Jupyter Server URL
    token : str
        Jupyter Server authentication token
    username : str
        [optional] Username using the kernel
    kernel_id : str
        [optional] Kernel id to connect to
    client_kwargs : dict[str, Any]
        [optional] Kernel client factory kwargs
    """

    def __init__(
        self,
        server_url: str,
        token: str,
        username: str = os.environ.get("USER", "username"),
        kernel_id: str | None = None,
        client_kwargs: dict[str, t.Any] | None = None,
        **kwargs,
    ):
        """Initialize the kernel manager."""
        super().__init__(**kwargs)
        self.server_url = server_url
        self.token = token
        self.username = username
        self.__kernel: dict | None = None
        self.__client: t.Any | None = None
        self.__client_kwargs = client_kwargs

        if kernel_id:
            self.__kernel = {
                "id": kernel_id,
                "execution_state": "unknown",
                "last_activity": datetime.datetime.strftime(
                    utcnow(), "%Y-%m-%dT%H:%M:%S.%fZ"
                ),
            }
            self.refresh_model()

    @property
    def has_kernel(self):
        """Has a kernel been started that we are managing."""
        return self.__kernel is not None

    @property
    def kernel(self) -> dict[str, t.Any] | None:
        """The kernel model"""
        return self.__kernel

    @property
    def kernel_url(self) -> str | None:
        if self.kernel:
            kernel_id = self.kernel["id"]
            return url_path_join(self.server_url, "api/kernels", kernel_id)
        else:
            return None

    client_class = DottedObjectName(
        "jupyter_kernel_client.wsclient.KernelWebSocketClient"
    )
    client_factory = Type(klass="jupyter_client.client.KernelClientABC")

    @default("client_factory")
    def _client_factory_default(self) -> Type:
        return import_item(self.client_class)

    @observe("client_class")
    def _client_class_changed(self, change: dict[str, DottedObjectName]) -> None:
        self.client_factory = import_item(str(change["new"]))

    # --------------------------------------------------------------------------
    # create a Client connected to our Kernel
    # --------------------------------------------------------------------------

    @property
    def client(self) -> t.Any:
        """Create a client configured to connect to our kernel."""
        if not self.kernel_url:
            raise RuntimeError(
                "You must first start a kernel before requesting a client."
            )

        if not self.__client:
            base_ws_url = HTTP_PROTOCOL_REGEXP.sub("ws", self.kernel_url, 1)

            kw: dict[str, t.Any] = {
                "endpoint": url_path_join(base_ws_url, "channels"),
                "token": self.token,
                "username": self.username,
                "log": self.log,
                "parent": self,
            }

            # add kwargs last, for manual overrides
            kw.update(self.__client_kwargs or {})
            self.__client = self.client_factory(**kw)

        return self.__client

    def refresh_model(
        self, timeout: float = REQUEST_TIMEOUT
    ) -> dict[str, t.Any] | None:
        """Refresh the kernel model.

        Returns
        -------
            The refreshed model kernel. If None, the kernel
            does not exist anymore.

        Raises
        ------
            RuntimeError : If no kernel managed
        """
        if not self.kernel_url:
            raise RuntimeError("You must first start a kernel.")

        self.log.debug("Request kernel at: %s", self.kernel_url)
        try:
            response = fetch(
                self.kernel_url, token=self.token, method="GET", timeout=timeout
            )
        except HTTPError as error:
            if error.response.status_code == 404:
                self.log.warning("Kernel not found at: %s", self.kernel_url)
                model = None
            else:
                raise
        else:
            model = response.json()
        self.log.debug("Kernel retrieved: %s", model)

        self.__kernel = model
        if self.__kernel is None and self.__client:
            self.__client.stop_channels()
            self.__client = None
        return model

    # --------------------------------------------------------------------------
    # Kernel management
    # --------------------------------------------------------------------------
    def start_kernel(
        self, name: str, path: str | None = None, timeout: float = REQUEST_TIMEOUT
    ) -> dict[str, t.Any]:
        """Starts a kernel via HTTP request.

        Parameters
        ----------
            name : str
                Kernel name
            path : str
                [optional] API path from root to the cwd of the kernel
            timeout : float
                Request timeout
        Returns
        -------
            The kernel model
        """
        if self.has_kernel:
            raise RuntimeError(
                "A kernel is already started. Shutdown it before starting a new one."
            )

        response = fetch(
            f"{self.server_url}/api/kernels",
            token=self.token,
            method="POST",
            json={"name": name, "path": path},
            timeout=timeout,
        )

        self.__kernel = response.json()
        if self.__client:
            self.__client.stop_channels()
            self.__client = None
        self.log.info("KernelHttpManager created a new kernel: %s", self.__kernel)
        return t.cast(dict[str, t.Any], self.__kernel)

    def shutdown_kernel(
        self, now: bool = False, restart: bool = False, timeout: float = REQUEST_TIMEOUT
    ):
        """Attempts to stop the kernel process cleanly via HTTP."""
        if not self.kernel_url:
            raise RuntimeError(
                "You must first start a kernel before requesting a client."
            )

        self.log.debug("Request shutdown kernel at: %s", self.kernel_url)
        if not now:
            self.client.shutdown(restart)
            count = 10
            while count:
                model = self.refresh_model()
                if model is None:
                    return
                count -= 1
                sleep(timeout / 10.0)

        # If not now and refreshing the model still returns it, try the http way
        try:
            response = fetch(
                self.kernel_url, token=self.token, method="DELETE", timeout=timeout
            )
            self.log.debug(
                "Shutdown kernel response: %d %s",
                response.status_code,
                response.reason,
            )
        except HTTPError as error:
            if error.response.status_code == 404:
                self.log.debug("Shutdown kernel response: kernel not found (ignored)")
            else:
                raise
        except BaseException as e:
            self.log.warning(
                "Unable to shutdown the kernel. The server is likely down; error: %s", e
            )
            self.log.debug("", exc_info=e)

    def restart_kernel(self, timeout: float = REQUEST_TIMEOUT, **kw):
        """Restarts a kernel via HTTP request."""
        if not self.kernel_url:
            raise RuntimeError(
                "You must first start a kernel before requesting a client."
            )

        kernel_url = self.kernel_url + "/restart"
        self.log.debug("Request restart kernel at: %s", kernel_url)
        response = fetch(kernel_url, token=self.token, method="POST", timeout=timeout)
        self.log.debug(
            "Restart kernel response: %d %s", response.status_code, response.reason
        )

    def interrupt_kernel(self, timeout: float = REQUEST_TIMEOUT):
        """Interrupts the kernel via an HTTP request."""
        if not self.kernel_url:
            raise RuntimeError(
                "You must first start a kernel before requesting a client."
            )

        kernel_url = self.kernel_url + "/interrupt"
        self.log.debug("Request interrupt kernel at: %s", kernel_url)
        response = fetch(
            kernel_url,
            token=self.token,
            method="POST",
            timeout=timeout,
        )
        self.log.debug(
            "Interrupt kernel response: %d %s",
            response.status_code,
            response.reason,
        )

    def signal_kernel(self, signum: int) -> None:
        """Send a signal to the kernel."""
        self.log.warning("Sending signal to kernel through websocket is not supported.")

    def is_alive(self, timeout: float = REQUEST_TIMEOUT):
        """Is the kernel process still running?"""
        if self.has_kernel:
            # Go ahead and issue a request to get the kernel
            self.__kernel = self.refresh_model(timeout)
        # Kernel may have 'disappeared'
        return self.has_kernel

    def cleanup_resources(self, restart=False):
        """Clean up resources when the kernel is shut down"""
        ...
