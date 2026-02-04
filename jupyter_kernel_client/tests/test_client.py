# Copyright (c) 2023-2024 Datalayer, Inc.
#
# BSD 3-Clause License

import asyncio
import os
from platform import node

import pytest
import numpy as np
import pandas as pd

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


def test_list_kernels_client(jupyter_server):
    port, token = jupyter_server

    # Start a kernel to ensure the list is not empty
    with KernelClient(server_url=f"http://localhost:{port}", token=token) as kernel:
        kernel_id = kernel.id

        # Use a new client to list the kernels
        listing_client = KernelClient(server_url=f"http://localhost:{port}", token=token)
        kernels = listing_client.list_kernels()

        assert isinstance(kernels, list)
        assert len(kernels) > 0

        # Check that the kernel we started is in the list
        found = False
        for k in kernels:
            assert "id" in k
            assert "name" in k
            if k["id"] == kernel_id:
                found = True

        assert found, f"Kernel with id {kernel_id} not found in the list of running kernels."


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
            size=None
        ),
        VariableDescription(
            name="b",
            type=["builtins", "str"],
            size=None
        ),
        VariableDescription(
            name="c",
            type=["builtins", "set"],
            size=None,
        ),
        VariableDescription(
            name="d",
            type=["builtins", "dict"],
            size=None,
        ),
    ]


@pytest.mark.parametrize(
    "variable,set_variable,expected",
    (
        ("a", "a = 1.0", ({"text/plain": "1.0"}, {})),
        ("b", 'b = "hello the world"', ({"text/plain": "'hello the world'"}, {})),
        ("c", "c = {3, 4, 5}", ({"text/plain": "{3, 4, 5}"}, {})),
        ("d", "d = {'name': 'titi'}", ({"text/plain": "{'name': 'titi'}"}, {})),
    ),
)
def test_get_all_mimetype_variables(jupyter_server, variable, set_variable, expected):
    port, token = jupyter_server

    with KernelClient(server_url=f"http://localhost:{port}", token=token) as kernel:
        kernel.execute(set_variable)

        values = kernel.get_variable_mimetypes(variable)

    assert values == expected


@pytest.mark.parametrize(
    "variable,set_variable,expected",
    (
        ("a", "a = 1.0", ({"text/plain": "1.0"}, {})),
        ("b", 'b = "hello the world"', ({"text/plain": "'hello the world'"}, {})),
        ("c", "c = {3, 4, 5}", ({"text/plain": "{3, 4, 5}"}, {})),
        ("d", "d = {'name': 'titi'}", ({"text/plain": "{'name': 'titi'}"}, {})),
    ),
)
def test_get_textplain_variables(jupyter_server, variable, set_variable, expected):
    port, token = jupyter_server

    with KernelClient(server_url=f"http://localhost:{port}", token=token) as kernel:
        kernel.execute(set_variable)

        values = kernel.get_variable_mimetypes(variable, "text/plain")

    assert values == expected


@pytest.mark.parametrize(
    "variable,value",
    (
        ("lst", [1, 2, 3, 4]),
        ("arr", np.random.randn(100000)),
        ("df", pd.DataFrame({'values': np.random.randn(1000), 'categories': np.random.choice(['A', 'B', 'C'], 1000), 'integers': np.random.randint(1, 100, 1000)})),
        ("s", pd.Series(np.random.randn(100000))),
    ),
)
def test_set_variable_and_get_variable(jupyter_server, variable, value):
    port, token = jupyter_server

    with KernelClient(server_url=f"http://localhost:{port}", token=token) as kernel:
        kernel.set_variable(variable, value)
        retrieved_value = kernel.get_variable(variable)

    if isinstance(value, pd.DataFrame):
        pd.testing.assert_frame_equal(value, retrieved_value)  # type: ignore
    elif isinstance(value, pd.Series):
        pd.testing.assert_series_equal(value, retrieved_value)  # type: ignore
    elif isinstance(value, np.ndarray):
        assert (value == retrieved_value).all()
    else:
        assert value == retrieved_value


@pytest.mark.parametrize(
    "variable,value",
    (
        ("lst", [1, 2, 3, 4]),
        ("arr", np.random.randn(10)),
    ),
)
def test_set_variables_on_execute(jupyter_server, variable, value):
    port, token = jupyter_server
    variables = {variable: value}
    with KernelClient(server_url=f"http://localhost:{port}", token=token) as kernel:
        reply = kernel.execute(f'print({variable})', variables=variables)
        assert reply["execution_count"] == 1
        assert reply["outputs"] == [
            {
                "output_type": "stream",
                "name": "stdout",
                "text": f"{value}\n",
            }
        ]
        assert reply["status"] == "ok"


@pytest.mark.parametrize(
    "variable,set_variable,expected",
    (
        ("a", "a = 1.0", ({"text/plain": "1.0"}, {})),
        ("b", 'b = "hello the world"', ({"text/plain": "'hello the world'"}, {})),
        ("c", "c = {3, 4, 5}", ({"text/plain": "{3, 4, 5}"}, {})),
        ("d", "d = {'name': 'titi'}", ({"text/plain": "{'name': 'titi'}"}, {})),
    ),
)
def test_set_variables(jupyter_server, variable, set_variable, expected):
    port, token = jupyter_server

    with KernelClient(server_url=f"http://localhost:{port}", token=token) as kernel:
        kernel.execute(set_variable)

        values = kernel.get_variable_mimetypes(variable)

    assert values == expected


@pytest.mark.asyncio
async def test_multi_execution_in_event_loop(jupyter_server):
    port, token = jupyter_server

    current_user = os.environ.get('USER', 'John Smith')
    current_node = node()

    with KernelClient(server_url=f"http://localhost:{port}", token=token) as kernel:
        all = await asyncio.gather(
            asyncio.to_thread(
                kernel.execute,
                f"""import os
from platform import node
import time
time.sleep(5)
print(f"Hey {{os.environ.get('USER', 'John Smith')}} from {{node()}}.")
"""
            ),
            asyncio.to_thread(
                kernel.execute,
                """import time
time.sleep(1)
print("Hello")"""
            ),
        )

        assert all[0]["execution_count"] == 1
        assert all[0]["outputs"] == [
            {
                "output_type": "stream",
                "name": "stdout",
                "text": f"Hey {current_user} from {current_node}.\n",
            }
        ]
        assert all[0]["status"] == "ok"

        assert all[1]["execution_count"] == 2
        assert all[1]["outputs"] == [
            {
                "output_type": "stream",
                "name": "stdout",
                "text": "Hello\n",
            }
        ]
        assert all[1]["status"] == "ok"
