# Copyright (c) 2023-2024 Datalayer, Inc.
#
# BSD 3-Clause License

"""Test the jupyter client using the latest SDK."""

import os
import time

import pytest
from datalayer_core import DatalayerClient

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


DATALAYER_TEST_TOKEN = os.environ.get("DATALAYER_TEST_TOKEN")


@pytest.mark.skipif(
    not bool(DATALAYER_TEST_TOKEN),
    reason="DATALAYER_TEST_TOKEN is not set, skipping secret tests.",
)
def test_runtime_creation():
    time.sleep(10)
    client = DatalayerClient()
    test_text = "Hello from the test runtime!"
    with client.create_runtime() as runtime:
        response = runtime.execute(f"print('{test_text}')")
        assert response.stdout == test_text + "\n"
    time.sleep(10)


@pytest.mark.skipif(
    not bool(DATALAYER_TEST_TOKEN),
    reason="DATALAYER_TEST_TOKEN is not set, skipping secret tests.",
)
def test_runtime_variables():
    time.sleep(10)
    client = DatalayerClient()
    test_text = "Hello from the test runtime!"
    with client.create_runtime() as runtime:
        response = runtime.execute(f"print(a)", variables={"a": test_text})
        assert response.stdout == test_text + '\n'
    time.sleep(10)


@pytest.mark.skipif(
    not bool(DATALAYER_TEST_TOKEN),
    reason="DATALAYER_TEST_TOKEN is not set, skipping secret tests.",
)
def test_runtime_output():
    time.sleep(10)
    client = DatalayerClient()
    test_text = 'Hello from the test runtime!'
    with client.create_runtime() as runtime:
        a = runtime.execute(f"a = '{test_text}'\nprint(a)", output='a')
        assert a == test_text
    time.sleep(10)
