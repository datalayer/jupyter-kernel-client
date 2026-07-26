# Copyright (c) 2023-2024 Datalayer, Inc.
#
# BSD 3-Clause License

"""Jupyter Kernel Client through websocket."""

from jupyter_kernel_client.__version__ import __version__
from jupyter_kernel_client.client import JupyterKernelClient
from jupyter_kernel_client.colab import ColabKernelClient, parse_colab_channels_url
from jupyter_kernel_client.kaggle import (
    KAGGLE_API_TOKEN_ENV,
    KaggleKernelClient,
    parse_kaggle_channels_url,
)
from jupyter_kernel_client.kaggle_execute import (
    KaggleExecutionResult,
    KaggleKernelExecutor,
)
from jupyter_kernel_client.interfaces import IJupyterKernelClient
from jupyter_kernel_client.konsoleapp import KonsoleApp
from jupyter_kernel_client.manager import KernelHttpManager
from jupyter_kernel_client.models import VariableDescription
from jupyter_kernel_client.snippets import SNIPPETS_REGISTRY, LanguageSnippets
from jupyter_kernel_client.utils import get_mimebundle_text
from jupyter_kernel_client.wsclient import JupyterSubprotocol, KernelWebSocketClient

__all__ = [
    "KAGGLE_API_TOKEN_ENV",
    "SNIPPETS_REGISTRY",
    "ColabKernelClient",
    "JupyterSubprotocol",
    "KaggleExecutionResult",
    "KaggleKernelClient",
    "KaggleKernelExecutor",
    "JupyterKernelClient",
    "IJupyterKernelClient",
    "KernelHttpManager",
    "KernelWebSocketClient",
    "KonsoleApp",
    "LanguageSnippets",
    "VariableDescription",
    "__version__",
    "get_mimebundle_text",
    "parse_colab_channels_url",
    "parse_kaggle_channels_url",
]
