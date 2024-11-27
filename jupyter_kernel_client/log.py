# Copyright (c) 2023-2024 Datalayer, Inc.
#
# BSD 3-Clause License

"""Grab the global logger instance.

This is a slight modification of traitlets code licensed under BSD 3-Clause License
Source: https://github.com/ipython/traitlets/blob/v5.14.3/traitlets/log.py
"""

from __future__ import annotations

import logging

_logger: logging.Logger | None = None


def get_logger() -> logging.Logger:
    """Grab the global logger instance.

    If a global Application is instantiated, grab its logger.
    Otherwise, grab the root logger.
    """
    global _logger

    if _logger is None:
        from traitlets.config import Application

        if Application.initialized():
            _logger = Application.instance().log
        else:
            _logger = logging.getLogger("jupyter_kernel_client")
            # Add a NullHandler to silence warnings about not being
            # initialized, per best practice for libraries.
            _logger.addHandler(logging.NullHandler())
    return _logger
