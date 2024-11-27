import os
import signal
import typing as t

from jupyter_core.application import JupyterApp, base_aliases, base_flags
from traitlets import CBool, CUnicode, Dict, Type, Unicode
from traitlets.config import boolean_flag, catch_config_error

from . import __version__
from .client import KernelClient
from .manager import KernelManager
from .shell import WSTerminalInteractiveShell

# -----------------------------------------------------------------------------
# Globals
# -----------------------------------------------------------------------------

_examples = """
jupyter connect # start the WS-based console
"""

# -----------------------------------------------------------------------------
# Flags and Aliases
# -----------------------------------------------------------------------------

# copy flags from mixin:
flags = dict(base_flags)
flags.update(
    boolean_flag(
        "confirm-exit",
        "BaseWsConsoleApp.confirm_exit",
        """Set to display confirmation dialog on exit. You can always use 'exit' or
       'quit', to force a direct exit without any confirmation. This can also
       be set in the config file by setting
       `c.BaseWsConsoleApp.confirm_exit`.
    """,
        """Don't prompt the user when exiting. This will terminate the kernel
       if it is owned by the frontend, and leave it alive if it is external.
       This can also be set in the config file by setting
       `c.BaseWsConsoleApp.confirm_exit`.
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

# copy flags from mixin
aliases = dict(base_aliases)
aliases.update(
    {
        "existing": "BaseWsConsoleApp.existing",
        "kernel": "BaseWsConsoleApp.kernel_name",
    }
)

# -----------------------------------------------------------------------------
# Classes
# -----------------------------------------------------------------------------


class BaseWsConsoleApp(JupyterApp):
    """Start a terminal frontend to a kernel."""

    name = "jupyter-connect"
    version = __version__

    description = """
        The Jupyter Kernels terminal-based Console.

        This launches a Console application inside a terminal.

        The Console supports various extra features beyond the traditional
        single-process Terminal IPython shell, such as connecting to an
        existing ipython session, via:

            jupyter connect --existing

        where the previous session could have been created by another jupyter
        console, or by opening a notebook.
    """
    examples = _examples

    classes = [WSTerminalInteractiveShell]
    flags = Dict(flags)
    aliases = Dict(aliases)

    subcommands = Dict()

    kernel_manager_class = Type(
        default_value=KernelManager,
        config=True,
        help="The kernel manager class to use.",
    )
    kernel_client_class = KernelClient

    existing = CUnicode("", config=True, help="""Connect to an already running kernel""")

    kernel_name = Unicode("", config=True, help="""The name of the kernel to connect to.""")

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
            manager=self.kernel_manager,
            client=self.kernel_client,  # FIXME
            confirm_exit=self.confirm_exit,
        )
        self.shell.own_kernel = (
            not self.existing  # FIXME test reusing existing kernel
        )

    def handle_sigint(self, *args):
        if self.shell._executing:
            if self.existing:
                self.log.error("Cannot interrupt kernels we didn't start.")
            else:
                self.kernel_manager.interrupt_kernel()
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

        self.kernel_manager = None
        self.kernel_client = None
        self.shell = None

        self.init_kernel_manager()
        self.init_kernel_client()

        if self.kernel_client.channels_running:
            # create the shell
            self.init_shell()
            # and draw the banner
            self.init_banner()

    def init_banner(self):
        """Optionally display the banner"""
        self.shell.show_banner()

    def init_kernel_manager(self) -> None:
        """Initialize the kernel manager."""
        raise NotImplementedError(
            "BaseWsConsoleApp.init_kernel_manager must be implemented in child class."
        )

    def init_kernel_client(self) -> None:
        """Initialize the kernel client."""
        self.kernel_client = self.kernel_manager.client()

        self.kernel_client.start_channels()

    def start(self):
        # JupyterApp.start dispatches on NoStart
        super().start()
        try:
            if self.shell is None:
                return
            self.log.debug("Starting the jupyter websocket console mainloop...")
            self.shell.mainloop()
        finally:
            self.kernel_client.stop_channels()


class WsConsoleApp(BaseWsConsoleApp):
    server_url = Unicode("", config=True, help="URL to the Jupyter Server.")

    # FIXME it does not support password
    token = Unicode("", config=True, help="Jupyter Server token.")

    username = Unicode(
        os.environ.get("USER", "username"),
        help="""Username for the client. Default is your system username.""",
        config=True,
    )

    def init_kernel_manager(self) -> None:
        """Initialize the kernel manager."""
        # Create a KernelManager and start a kernel.
        try:
            # FIXME
            self.kernel_manager = self.kernel_manager_class(
                parent=self,
                kernel_name=self.kernel_name,
                server_url=self.server_url,
                token=self.token,
            )

            if not self.existing:
                # access kernel_spec to ensure the NoSuchKernel error is raised
                # if it's going to be
                kernel_spec = self.kernel_manager.kernel_spec  # noqa: F841
        except NoSuchKernel:
            self.log.critical("Could not find kernel %r", self.kernel_name)
            self.exit(1)  # type:ignore[attr-defined]

        self.kernel_manager = t.cast(KernelManager, self.kernel_manager)
        self.kernel_manager.client_factory = self.kernel_client_class

        if not self.existing:
            # FIXME
            self.kernel_manager.start_kernel(**kwargs)
            # self.kernel_manager.start_kernel(kernel_name=self.kernel_name)


main = launch_new_instance = WsConsoleApp.launch_instance


if __name__ == "__main__":
    main()
