# Copyright (c) 2023-2024 Datalayer, Inc.
#
# BSD 3-Clause License

import os
from platform import node

import pytest

from jupyter_kernel_client import KernelClient, VariableDescription


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


def test_list_variables(jupyter_server):
    port, token = jupyter_server

    with KernelClient(server_url=f"http://localhost:{port}", token=token) as kernel:
        kernel.execute(
            """a = 1.0
b = "hello the world"
c = {3, 4, 5}
d = {"name": "titi"}
"""
        )

        variables = kernel.list_variables()

    assert variables == [
        VariableDescription(
            name="a",
            type=["builtins", "float"],
        ),
        VariableDescription(
            name="b",
            type=["builtins", "str"],
        ),
        VariableDescription(
            name="c",
            type=["builtins", "set"],
        ),
        VariableDescription(
            name="d",
            type=["builtins", "dict"],
        ),
    ]


@pytest.mark.parametrize(
    "variable,set_variable,expected",
    (
        ("a", "a = 1.0", {"text/plain": "1.0"}),
        ("b", 'b = "hello the world"', {"text/plain": "'hello the world'"}),
        ("c", "c = {3, 4, 5}", {"text/plain": "{3, 4, 5}"}),
        ("d", "d = {'name': 'titi'}", {"text/plain": "{'name': 'titi'}"}),
    ),
)
def test_get_all_mimetype_variables(jupyter_server, variable, set_variable, expected):
    port, token = jupyter_server

    with KernelClient(server_url=f"http://localhost:{port}", token=token) as kernel:
        kernel.execute(set_variable)

        values = kernel.get_variable(variable)

    assert values == expected


@pytest.mark.parametrize(
    "variable,set_variable,expected",
    (
        ("a", "a = 1.0", {"text/plain": "1.0"}),
        ("b", 'b = "hello the world"', {"text/plain": "'hello the world'"}),
        ("c", "c = {3, 4, 5}", {"text/plain": "{3, 4, 5}"}),
        ("d", "d = {'name': 'titi'}", {"text/plain": "{'name': 'titi'}"}),
    ),
)
def test_get_textplain_variables(jupyter_server, variable, set_variable, expected):
    port, token = jupyter_server

    with KernelClient(server_url=f"http://localhost:{port}", token=token) as kernel:
        kernel.execute(set_variable)

        values = kernel.get_variable(variable, "text/plain")

    assert values == expected
