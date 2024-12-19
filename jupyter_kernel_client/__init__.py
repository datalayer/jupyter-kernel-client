# Copyright (c) 2023-2024 Datalayer, Inc.
#
# BSD 3-Clause License

"""Jupyter Kernel Client through websocket."""

from ._version import __version__
from .client import KernelClient
from .konsoleapp import KonsoleApp
from .manager import KernelHttpManager
from .models import VariableDescription
from .snippets import SNIPPETS_REGISTRY, LanguageSnippets
from .wsclient import KernelWebSocketClient

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
