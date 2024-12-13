# Copyright (c) 2023-2024 Datalayer, Inc.
#
# BSD 3-Clause License

from __future__ import annotations

import asyncio

from jupyter_core.utils import ensure_async
from traitlets import (
    Instance,
    default,
)

from . import __version__

try:
    from jupyter_console.ptshell import ZMQTerminalInteractiveShell

    class WSTerminalInteractiveShell(ZMQTerminalInteractiveShell):
        manager = Instance("jupyter_kernel_client.manager.KernelHttpManager", allow_none=True)
        client = Instance("jupyter_kernel_client.wsclient.KernelWebSocketClient", allow_none=True)

        @default("banner")
        def _default_banner(self):
            return "Jupyter Kernel console {version}\n\n{kernel_banner}"

        async def handle_external_iopub(self, loop=None):
            while self.keep_running:
                # we need to check for keep_running from time to time
                poll_result = await ensure_async(self.client.iopub_channel.msg_ready)
                if poll_result:
                    self.handle_iopub()
                await asyncio.sleep(0.5)

        def show_banner(self):
            print(  # noqa T201
                self.banner.format(
                    version=__version__, kernel_banner=self.kernel_info.get("banner", "")
                ),
                end="",
                flush=True,
            )

        def check_complete(self, code: str) -> tuple[bool, str]:
            r = super().check_complete(code)
            if self.use_kernel_is_complete:
                # Flush iopub linked to complete request
                # Without this, handling input does not work
                self.handle_iopub()
            return r

except ModuleNotFoundError:

    class WSTerminalInteractiveShell:
        def __init__(self):
            self._executing = False

        def show_banner(self):
            return "You must install `jupyter_console` to use the console:\n\n\tpip install jupyter-console\n"  # noqa E501

        def mainloop(self) -> None:
            raise ModuleNotFoundError("jupyter_console")
