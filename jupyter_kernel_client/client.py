# Copyright (c) 2023-2024 Datalayer, Inc.
#
# BSD 3-Clause License

from __future__ import annotations

import datetime
import logging
import typing as t
from functools import partial

from traitlets import Type
from traitlets.config import LoggingConfigurable

from .constants import REQUEST_TIMEOUT
from .log import get_logger
from .manager import KernelHttpManager
from .models import VariableDescription
from .snippets import SNIPPETS_REGISTRY
from .utils import UTC


def output_hook(outputs: list[dict[str, t.Any]], message: dict[str, t.Any]) -> set[int]:  # noqa: C901
    """Callback on messages captured during a code snippet execution.

    The return list of updated output will be empty if no output where changed.
    It will equal all indexes if the outputs was cleared.

    Example:
        This callback is meant to be used with ``KernelClient.execute_interactive``::

            from functools from partial
            from jupyter_kernel_client import KernelClient
            with KernelClient(server_url, token) as kernel:
                outputs = []
                kernel.execute_interactive(
                    "print('hello')",
                    output_hook=partial(output_hook, outputs)
                )
                print(outputs)

    Args:
        outputs: List in which to append the output
        message: A kernel message

    Returns:
        list of output indexed updated
    """
    msg_type = message["header"]["msg_type"]
    content = message["content"]

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
        # FIXME Logic is quite complex at https://github.com/jupyterlab/jupyterlab/blob/7ae2d436fc410b0cff51042a3350ba71f54f4445/packages/outputarea/src/model.ts#L518
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
        size = len(outputs)
        outputs.clear()
        return set(range(size))
    elif msg_type == "update_display_data":
        display_id = content.get("transient", {}).get("display_id")
        indexes = set()
        if display_id:
            for index, obsolete_update in enumerate(outputs):
                if obsolete_update.get("transient", {}).get("display_id") == display_id:
                    obsolete_update["metadata"] = content["metadata"]
                    obsolete_update["data"] = content["data"]
                    indexes.add(index)

        return indexes

    if output:
        index = len(outputs)
        outputs.append(output)
        return {index}

    return set()


class KernelClient(LoggingConfigurable):
    """Jupyter Kernel Client

    Example:
        You need to start JupyterLab or Jupyter notebook. You must write down
        the server URL and the authentication token from the link looking like::

            http://localhost:8888/...?token=abcedfgh...
            <--  server URL   -->           <--token-->

        In another terminal, start a Python console. In which you can test the
        following snippet::

            import os
            from platform import node
            from jupyter_kernel_client import KernelClient

            with KernelClient(server_url="http://localhost:8888", token="abcedfgh...") as kernel:
                reply = kernel.execute(
                    "import os\nfrom platform import node\nprint(f\"Hey {os.environ.get('USER', 'John Smith')} from {node()}.\")"
                )

                assert reply["execution_count"] == 1
                assert reply["outputs"] == [
                    {
                        "output_type": "stream",
                        "name": "stdout",
                        "text": f"Hey {os.environ.get('USER', 'John Smith')} from {node()}.\n",
                    }
                ]
                assert reply["status"] == "ok"

    Note:
        By default it connects to an Jupyter Server through the following arguments.

        Those arguments may be different if the ``kernel_manager_class`` is modified.

    Args:
        server_url: str
            Jupyter Server URL; for example ``http://localhost:8888``
        token: str
            Jupyter Server authentication token
        username: str
            Client user name; default to environment variable USER
        kernel_id: str | None
            ID of the kernel to connect to
    """  # noqa E501

    kernel_manager_class = Type(
        default_value=KernelHttpManager,
        config=True,
        help="The kernel manager class to use.",
    )

    def __init__(
        self, kernel_id: str | None = None, log: logging.Logger | None = None, **kwargs
    ) -> None:
        super().__init__(log=log or get_logger())
        self._manager = self.kernel_manager_class(parent=self, kernel_id=kernel_id, **kwargs)
        # Set it after the manager as if a kernel_id is provided,
        # we will try to connect to it.
        self._own_kernel = self._manager.kernel is None

    def __del__(self) -> None:
        try:
            self.stop()
        except BaseException as e:
            self.log.error(
                "Failed to stop the kernel client for %s.", self._manager.kernel_url, exc_info=e
            )

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
    def kernel_info(self) -> dict[str, t.Any] | None:
        """Kernel information.

        This is the dictionary returned by the kernel for a kernel_info_request.

        Returns:
            The kernel information
        """
        if self._manager.kernel:
            return self._manager.client.kernel_info_interactive(timeout=REQUEST_TIMEOUT)

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

    @property
    def username(self) -> str:
        """Client owner username."""
        return self._manager.username

    @property
    def server_url(self) -> str:
        """Kernel server URL."""
        return self._manager.server_url

    def execute(
        self,
        code: str,
        silent: bool = False,
        store_history: bool = True,
        user_expressions: dict[str, t.Any] | None = None,
        allow_stdin: bool | None = False,
        stop_on_error: bool = True,
        timeout: float = REQUEST_TIMEOUT,
        stdin_hook: t.Callable[[dict[str, t.Any]], None] | None = None,
    ) -> dict[str, t.Any]:
        """Execute code in the kernel

        Args:
            code: A string of code in the kernel's language.
            silent: optional (default False) If set, the kernel will execute the code as quietly
                possible, and will force store_history to be False.
            store_history: optional (default True) If set, the kernel will store command history.
                This is forced to be False if silent is True.
            user_expressions: optional, A dict mapping names to expressions to be evaluated in the
                user's dict. The expression values are returned as strings formatted using
                :func:`repr`.
            allow_stdin: optional (default False)
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

        reply = self._manager.client.execute_interactive(
            code,
            silent=silent,
            store_history=store_history,
            user_expressions=user_expressions,
            allow_stdin=allow_stdin,
            stop_on_error=stop_on_error,
            timeout=timeout,
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
        timeout: float | None = REQUEST_TIMEOUT,
        output_hook: t.Callable[[dict[str, t.Any]], None] | None = None,
        stdin_hook: t.Callable[[dict[str, t.Any]], None] | None = None,
    ) -> dict[str, t.Any]:
        """Execute code in the kernel with low-level API

        Output will be redisplayed, and stdin prompts will be relayed as well.

        You can pass a custom output_hook callable that will be called
        with every IOPub message that is produced instead of the default redisplay.

        Args:
            code: A string of code in the kernel's language.
            silent: optional (default False)
                If set, the kernel will execute the code as quietly possible, and
                will force store_history to be False.
            store_history: optional (default True)
                If set, the kernel will store command history.  This is forced
                to be False if silent is True.
            user_expressions: optional
                A dict mapping names to expressions to be evaluated in the user's
                dict. The expression values are returned as strings formatted using
                :func:`repr`.
            allow_stdin: optional
                Flag for whether the kernel can send stdin requests to frontends.
            stop_on_error: optional (default True)
                Flag whether to abort the execution queue, if an exception is encountered.
            timeout: (default: REQUEST_TIMEOUT)
                Timeout to use when waiting for a reply
            output_hook:
                Function to be called with output messages.
                If not specified, output will be redisplayed.
            stdin_hook:
                Function to be called with stdin_request messages.
                If not specified, input/getpass will be called.

        Returns:
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

    def __enter__(self) -> KernelClient:
        self.start()
        return self

    def __exit__(self, exc_type, exc_value, exc_tb) -> None:
        self.stop()

    def start(
        self,
        name: str = "python3",
        path: str | None = None,
        timeout: float = REQUEST_TIMEOUT,
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

    #
    # Variables related methods
    #
    def get_variable(
        self, name: str, mimetype: str | None = None
    ) -> tuple[dict[str, t.Any], dict[str, t.Any]]:
        """Get a kernel variable.

        Args:
            name: Variable name
            mimetype: optional, type of variable value serialization; default ``None``,
                i.e. returns all known serialization.

        Returns:
            A tuple of dictionaries for which keys are mimetype and values the variable value
            serialized in that mimetype for the first dictionary and metadata in the second one.
            Even if a mimetype is specified, the dictionary may not contain it if
            the kernel introspection failed to get the variable in the specified format.
        Raises:
            ValueError: If the kernel programming language is not supported
            RuntimeError: If the kernel introspection failed
        """
        kernel_language = (self.kernel_info or {}).get("language_info", {}).get("name")
        if kernel_language not in SNIPPETS_REGISTRY.available_languages:
            raise ValueError(f"""Code snippet for language {kernel_language} are not available.
You can set them yourself using:

    from jupyter_kernel_client import SNIPPETS_REGISTRY, LanguageSnippets
    SNIPPETS_REGISTRY.register("my-language", LanguageSnippets(list_variables="", get_variable=""))
""")

        snippet = SNIPPETS_REGISTRY.get_get_variable(kernel_language)
        results = self.execute(snippet.format(name=name, mimetype=mimetype), silent=True)

        self.log.debug("Kernel variables: %s", results)

        if results["status"] == "ok" and results["outputs"]:
            if mimetype is None:
                return results["outputs"][0]["data"], results["outputs"][0].get("metadata", {})
            else:

                def filter_dict(d: dict, mimetype: str) -> dict:
                    if mimetype in d:
                        return {mimetype: d[mimetype]}
                    else:
                        return {}

                return (
                    filter_dict(results["outputs"][0]["data"], mimetype),
                    filter_dict(results["outputs"][0].get("metadata", {}), mimetype),
                )
        else:
            raise RuntimeError(f"Failed to get variable {name} with type {mimetype}.")

    def list_variables(self) -> list[VariableDescription]:
        """List the kernel global variables.

        Returns:
            The list of global variables.
        Raises:
            ValueError: If the kernel programming language is not supported
            RuntimeError: If the kernel introspection failed
        """
        kernel_language = (self.kernel_info or {}).get("language_info", {}).get("name")
        if kernel_language not in SNIPPETS_REGISTRY.available_languages:
            raise ValueError(f"""Code snippet for language {kernel_language} are not available.
You can set them yourself using:

    from jupyter_kernel_client import SNIPPETS_REGISTRY, LanguageSnippets
    SNIPPETS_REGISTRY.register("my-language", LanguageSnippets(list_variables="", get_variable=""))
""")

        snippet = SNIPPETS_REGISTRY.get_list_variables(kernel_language)
        results = self.execute(snippet, silent=True)

        self.log.debug("Kernel variables: %s", results)

        if (
            results["status"] == "ok"
            and results["outputs"]
            and "application/json" in results["outputs"][-1]["data"]
        ):
            return sorted(
                (
                    VariableDescription(**v)
                    for v in results["outputs"][-1]["data"]["application/json"]
                ),
                key=lambda v: v["name"],
            )
        else:
            raise RuntimeError("Failed to list variables.")
