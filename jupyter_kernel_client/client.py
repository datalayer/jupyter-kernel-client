from __future__ import annotations

import datetime
import typing as t
from functools import partial

from traitlets import Type
from traitlets.config import LoggingConfigurable

from .constants import REQUEST_TIMEOUT
from .manager import KernelHttpManager
from .utils import UTC


class KernelClient(LoggingConfigurable):
    """Jupyter Kernel Client

    By default it connects to an Jupyter Server through the following arguments.

    Those arguments may be different if the ``kernel_manager_class`` is modified

    Args:
        server_url: str
            Jupyter Server URL; for example ``http://localhost:8888``
        token: str
            Jupyter Server authentication token
        username: str
            Client user name; default to environment variable USER
        kernel_id: str | None
            ID of the kernel to connect to
    """

    kernel_manager_class = Type(
        default_value=KernelHttpManager,
        config=True,
        help="The kernel manager class to use.",
    )

    def __init__(self, kernel_id: str | None = None, **kwargs) -> None:
        super().__init__()
        self._own_kernel = bool(kernel_id)
        self._manager = self.kernel_manager_class(parent=self, kernel_id=kernel_id, **kwargs)

    def __del__(self) -> None:
        self.stop()

    @property
    def execution_state(self) -> str | None:
        """Kernel process execution state.

        This can only be trusted after a call to ``KernelClient.refresh``.
        """
        return self._manager.kernel["execution_state"] if self._manager.kernel else None

    @property
    def has_kernel(self):
        """Is the client connected to an running kernel process?"""
        return self._manager.has_kernel

    @property
    def id(self) -> str | None:
        """Kernel ID"""
        return self._manager.kernel["id"] if self._manager.kernel else None

    @property
    def last_activity(self) -> datetime.datetime | None:
        """Kernel process last activity.

        This can only be trusted after a call to ``KernelClient.refresh``.
        """
        return (
            datetime.datetime.strptime(
                self._manager.kernel["last_activity"], "%Y-%m-%dT%H:%M:%S.%fZ"
            ).replace(tzinfo=UTC)
            if self._manager.kernel
            else None
        )

    def execute(  # noqa: C901
        self,
        code: str,
        silent: bool = False,
        store_history: bool = True,
        user_expressions: dict[str, t.Any] | None = None,
        allow_stdin: bool | None = None,
        stop_on_error: bool = True,
        timeout: float = REQUEST_TIMEOUT,
        stdin_hook: t.Callable[[dict[str, t.Any]], None] | None = None,
    ) -> dict[str, t.Any]:
        """Execute code in the kernel interactively

        Args:
            code: A string of code in the kernel's language.
            silent: optional (default False) If set, the kernel will execute the code as quietly possible, and
                will force store_history to be False.
            store_history: optional (default True) If set, the kernel will store command history.  This is forced
                to be False if silent is True.
            user_expressions: optional, A dict mapping names to expressions to be evaluated in the user's
                dict. The expression values are returned as strings formatted using
                :func:`repr`.
            allow_stdin: optional (default self.allow_stdin)
                Flag for whether the kernel can send stdin requests to frontends.
            stop_on_error: optional (default True)
                Flag whether to abort the execution queue, if an exception is encountered.
            timeout:
                Timeout to use when waiting for a reply
            stdin_hook:
                Function to be called with stdin_request messages.
                If not specified, input/getpass will be called.

        Returns:
            Execution results {"execution_count": int | None, "status": str, "outputs": list[dict]}

            The outputs will follow the structure of nbformat outputs.
        """
        outputs = []

        def output_hook(outputs: list[dict], msg: dict) -> None:
            msg_type = msg["header"]["msg_type"]
            content = msg["content"]

            output = None
            # Taken from https://github.com/jupyter/nbformat/blob/v5.10.4/nbformat/v4/nbbase.py#L73
            if msg_type == "execute_result":
                output = {
                    "output_type": msg_type,
                    "metadata": content["metadata"],
                    "data": content["data"],
                    "execution_count": content["execution_count"],
                }
            elif msg_type == "stream":
                output = {
                    "output_type": msg_type,
                    "name": content["name"],
                    "text": content["text"],
                }
            elif msg_type == "display_data":
                output = {
                    "output_type": msg_type,
                    "metadata": content["metadata"],
                    "data": content["data"],
                    "transient": content["transient"],
                }
            elif msg_type == "error":
                output = {
                    "output_type": msg_type,
                    "ename": content["ename"],
                    "evalue": content["evalue"],
                    "traceback": content["traceback"],
                }
            elif msg_type == "clear_output":
                # Ignore wait as we run without display
                outputs.clear()
            elif msg_type == "update_display_data":
                display_id = content.get("transient", {}).get("display_id")
                if display_id:
                    for obsolete_update in filter(
                        lambda o: o.get("transient", {}).get("display_id") == display_id, outputs
                    ):
                        obsolete_update["metadata"] = content["metadata"]
                        obsolete_update["data"] = content["data"]

            if output:
                outputs.append(output)

        reply = self._manager.client.execute_interactive(
            code,
            silent,
            store_history,
            user_expressions,
            allow_stdin,
            stop_on_error,
            timeout,
            output_hook=partial(output_hook, outputs),
            stdin_hook=stdin_hook,
        )

        reply_content = reply["content"]

        # Clean transient information
        # See https://jupyter-client.readthedocs.io/en/stable/messaging.html#display-data
        for output in outputs:
            if "transient" in output:
                del output["transient"]

        return {
            "execution_count": reply_content.get("execution_count"),
            "outputs": outputs,
            "status": reply_content["status"],
        }

    def execute_interactive(
        self,
        code: str,
        silent: bool = False,
        store_history: bool = True,
        user_expressions: dict[str, t.Any] | None = None,
        allow_stdin: bool | None = None,
        stop_on_error: bool = True,
        timeout: float | None = None,
        output_hook: t.Callable | None = None,
        stdin_hook: t.Callable | None = None,
    ) -> dict[str, t.Any]:
        """Execute code in the kernel with low-level API

        Output will be redisplayed, and stdin prompts will be relayed as well.

        You can pass a custom output_hook callable that will be called
        with every IOPub message that is produced instead of the default redisplay.

        Parameters
        ----------
        code : str
            A string of code in the kernel's language.

        silent : bool, optional (default False)
            If set, the kernel will execute the code as quietly possible, and
            will force store_history to be False.

        store_history : bool, optional (default True)
            If set, the kernel will store command history.  This is forced
            to be False if silent is True.

        user_expressions : dict, optional
            A dict mapping names to expressions to be evaluated in the user's
            dict. The expression values are returned as strings formatted using
            :func:`repr`.

        allow_stdin : bool, optional (default self.allow_stdin)
            Flag for whether the kernel can send stdin requests to frontends.

        stop_on_error: bool, optional (default True)
            Flag whether to abort the execution queue, if an exception is encountered.

        timeout: float or None (default: None)
            Timeout to use when waiting for a reply

        output_hook: callable(msg)
            Function to be called with output messages.
            If not specified, output will be redisplayed.

        stdin_hook: callable(msg)
            Function to be called with stdin_request messages.
            If not specified, input/getpass will be called.

        Returns
        -------
        reply: dict
            The reply message for this request
        """
        return self._manager.client.execute_interactive(
            code,
            silent=silent,
            store_history=store_history,
            user_expressions=user_expressions,
            allow_stdin=allow_stdin,
            stop_on_error=stop_on_error,
            timeout=timeout,
            output_hook=output_hook,
            stdin_hook=stdin_hook,
        )

    def interrupt(self, timeout: float = REQUEST_TIMEOUT) -> None:
        """Interrupts the kernel."""
        self._manager.interrupt_kernel(timeout=timeout)

    def is_alive(self, timeout: float = REQUEST_TIMEOUT) -> bool:
        """Is the kernel process still running?"""
        return self._manager.is_alive()

    def restart(self, timeout: float = REQUEST_TIMEOUT) -> None:
        """Restarts a kernel."""
        return self._manager.restart_kernel(timeout=timeout)

    def __enter__(self) -> "KernelClient":
        self.start()
        return self

    def __exit__(self, exc_type, exc_value, exc_tb) -> None:
        self.stop()

    def start(
        self, name: str = "python3", path: str | None = None, timeout: float = REQUEST_TIMEOUT
    ) -> None:
        """Connect to a kernel.

        If no ``kernel_id`` is provided when creating the client, it will
        start a new kernel using the provided ``name`` and ``path``.

        Args:
            name: Kernel specification name
            path: Current working directory of the kernel relative to the server root path
                It may not apply depending on the kernel provider.
            timeout: Request timeout in seconds

        """
        if not self._manager.has_kernel:
            self._manager.start_kernel(name=name, path=path, timeout=timeout)

        self._manager.client.start_channels()

    def stop(
        self,
        shutdown_kernel: bool | None = None,
        shutdown_now: bool = True,
        timeout: float = REQUEST_TIMEOUT,
    ) -> None:
        """Stop the connection to a kernel.

        Args:
            shutdown_kernel: Shut down the connected kernel;
                default True if the kernel was started by the client.
            shutdown_now: Whether to shut down the kernel now through a HTTP request
                or defer it by sending a shutdown-request message to the kernel process
            timeout: Request timeout in seconds
        """
        if self._manager.has_kernel:
            self._manager.client.stop_channels()
            shutdown = self._own_kernel if shutdown_kernel is None else shutdown_kernel
            if shutdown:
                self._manager.shutdown_kernel(now=shutdown_now, timeout=timeout)
