# Copyright (c) 2023-2024 Datalayer, Inc.
#
# BSD 3-Clause License

import os
from platform import node

from jupyter_kernel_client import KernelClient


def test_execution_as_context_manager(jupyter_server):
    port, token = jupyter_server

    with KernelClient(server_url=f"http://localhost:{port}", token=token) as kernel:
        reply = kernel.execute(
            """import os
from platform import node
print(f"Hey {os.environ.get('USER', 'John Smith')} from {node()}.")
"""
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


def test_execution_no_context_manager(jupyter_server):
    port, token = jupyter_server

    kernel = KernelClient(server_url=f"http://localhost:{port}", token=token)
    kernel.start()
    try:
        reply = kernel.execute(
            """import os
from platform import node
print(f"Hey {os.environ.get('USER', 'John Smith')} from {node()}.")
"""
        )
    finally:
        kernel.stop()

    assert reply["execution_count"] == 1
    assert reply["outputs"] == [
        {
            "output_type": "stream",
            "name": "stdout",
            "text": f"Hey {os.environ.get('USER', 'John Smith')} from {node()}.\n",
        }
    ]
    assert reply["status"] == "ok"
