# Copyright (c) 2023-2024 Datalayer, Inc.
#
# BSD 3-Clause License

"""Jupyter Kernel Client through websocket."""

from jupyter_kernel_client._version import __version__
from jupyter_kernel_client.client import KernelClient
from jupyter_kernel_client.konsoleapp import KonsoleApp
from jupyter_kernel_client.manager import KernelHttpManager
from jupyter_kernel_client.models import VariableDescription
from jupyter_kernel_client.snippets import SNIPPETS_REGISTRY, LanguageSnippets
from jupyter_kernel_client.wsclient import KernelWebSocketClient


__all__ = [
    "SNIPPETS_REGISTRY",
    "KernelClient",
    "KernelHttpManager",
    "KernelWebSocketClient",
    "KonsoleApp",
    "LanguageSnippets",
    "VariableDescription",
    "__version__",
]
