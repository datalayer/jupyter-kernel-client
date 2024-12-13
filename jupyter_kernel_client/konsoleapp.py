# Copyright (c) 2023-2024 Datalayer, Inc.
#
# BSD 3-Clause License

from __future__ import annotations

import os
import signal
import typing as t

from jupyter_core.application import JupyterApp, base_aliases, base_flags
from traitlets import CBool, CUnicode, Dict, Type, Unicode
from traitlets.config import boolean_flag, catch_config_error

from . import __version__
from .manager import KernelHttpManager
from .shell import WSTerminalInteractiveShell

# -----------------------------------------------------------------------------
# Globals
# -----------------------------------------------------------------------------

_examples = """
# Start a console connected to a local Jupyter Server running at http://localhost:8888 with a new python kernel.
jupyter konsole --token <server_token>

# Start a console connected to a distant Jupyter Server with a new python kernel.
jupyter konsole --url https://my.jupyter-server.xzy --token <server_token>
"""  # noqa E501

# -----------------------------------------------------------------------------
# Flags and Aliases
# -----------------------------------------------------------------------------

# copy flags from mixin:
flags = dict(base_flags)
flags.update(
    boolean_flag(
        "confirm-exit",
        "KonsoleApp.confirm_exit",
        """Set to display confirmation dialog on exit. You can always use 'exit' or
       'quit', to force a direct exit without any confirmation. This can also
       be set in the config file by setting
       `c.KonsoleApp.confirm_exit`.
    """,
        """Don't prompt the user when exiting. This will terminate the kernel
       if it is owned by the frontend, and leave it alive if it is external.
       This can also be set in the config file by setting
       `c.KonsoleApp.confirm_exit`.
    """,
    )
)
flags.update(
    boolean_flag(
        "simple-prompt",
        "WSTerminalInteractiveShell.simple_prompt",
        "Force simple minimal prompt using `raw_input`",
        "Use a rich interactive prompt with prompt_toolkit",
    )
)

# copy aliases from mixin
aliases = dict(base_aliases)
aliases.update(
    {
        "existing": "KonsoleApp.existing",
        "kernel": "KonsoleApp.kernel_name",
        "token": "KonsoleApp.token",
        "url": "KonsoleApp.server_url",
    }
)


# -----------------------------------------------------------------------------
# Classes
# -----------------------------------------------------------------------------


class KonsoleApp(JupyterApp):
    """Start a terminal frontend to a kernel."""

    name = "jupyter-konsole"
    version = __version__

    description = """
        The Jupyter Kernels terminal-based Console.

        This launches a Console application inside a terminal.

        By default it will connect to a local Jupyter Server running at http://localhost:8888
        and will create a new python kernel.

        The Console supports various extra features beyond the traditional
        single-process Terminal IPython shell, such as connecting to an
        existing jupyter kernel, via:

            jupyter konsole --token <server token> --existing <kernel_id>

        where the previous session could have been created by another jupyter
        console, or by opening a notebook.
    """
    examples = _examples

    classes = [WSTerminalInteractiveShell]  # noqa RUF012
    flags = Dict(flags)
    aliases = Dict(aliases)

    subcommands = Dict()

    server_url = Unicode("http://localhost:8888", config=True, help="URL to the Jupyter Server.")

    # FIXME it does not support password
    token = Unicode("", config=True, help="Jupyter Server token.")

    username = Unicode(
        os.environ.get("USER", "username"),
        help="""Username for the client. Default is your system username.""",
        config=True,
    )

    kernel_manager_class = Type(
        default_value=KernelHttpManager,
        config=True,
        help="The kernel manager class to use.",
    )

    existing = CUnicode("", config=True, help="""Existing kernel ID to connect to.""")

    kernel_name = Unicode("python3", config=True, help="""The name of the kernel to connect to.""")

    kernel_path = Unicode(
        "", config=True, help="API path from server root to the kernel working directory."
    )

    confirm_exit = CBool(
        True,
        config=True,
        help="""
        Set to display confirmation dialog on exit. You can always use 'exit' or 'quit',
        to force a direct exit without any confirmation.""",
    )

    force_interact = True

    def init_shell(self):
        # relay sigint to kernel
        signal.signal(signal.SIGINT, self.handle_sigint)
        self.shell = WSTerminalInteractiveShell.instance(
            parent=self,
            manager=self.kernel_client,
            client=self.kernel_client.client,
            confirm_exit=self.confirm_exit,
        )
        self.shell.own_kernel = not self.existing

    def handle_sigint(self, *args):
        if self.shell._executing:
            if self.existing:
                self.log.error("Cannot interrupt kernels we didn't start.")
            else:
                self.kernel_client.interrupt_kernel()
        else:
            # raise the KeyboardInterrupt if we aren't waiting for execution,
            # so that the interact loop advances, and prompt is redrawn, etc.
            raise KeyboardInterrupt

    @catch_config_error
    def initialize(self, argv: t.Any = None) -> None:
        """Do actions after construct, but before starting the app."""
        super().initialize(argv)
        if getattr(self, "_dispatching", False):
            return

        self.kernel_client = None
        self.shell = None

        self.init_kernel_manager()
        self.init_kernel_client()

        if self.kernel_client.client.channels_running:
            # create the shell
            self.init_shell()
            # and draw the banner
            self.init_banner()

    def init_banner(self):
        """Optionally display the banner"""
        self.shell.show_banner()

    def init_kernel_manager(self) -> None:
        """Initialize the kernel manager."""
        # Create a KernelManager and start a kernel.
        self.kernel_client = self.kernel_manager_class(
            parent=self,
            server_url=self.server_url,
            token=self.token,
            kernel_id=self.existing,
        )

        if not self.existing:
            self.kernel_client.start_kernel(name=self.kernel_name, path=self.kernel_path)
        elif self.kernel_client.kernel is None:
            msg = f"Unable to connect to kernel with ID {self.existing}."
            raise RuntimeError(msg)

    def init_kernel_client(self) -> None:
        """Initialize the kernel client."""
        self.kernel_client.client.start_channels()

    def start(self):
        # JupyterApp.start dispatches on NoStart
        super().start()
        try:
            if self.shell is None:
                return
            self.log.debug("Starting the jupyter websocket console mainloop...")
            self.shell.mainloop()
        finally:
            self.kernel_client.client.stop_channels()


main = launch_new_instance = KonsoleApp.launch_instance


if __name__ == "__main__":
    main()
