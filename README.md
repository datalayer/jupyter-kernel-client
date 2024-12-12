<!--
  ~ Copyright (c) 2023-2024 Datalayer, Inc.
  ~
  ~ BSD 3-Clause License
-->

# Jupyter Kernel Client (through http)

[![Github Actions Status](https://github.com/datalayer/jupyter-kernel-client/workflows/Build/badge.svg)](https://github.com/datalayer/jupyter-kernel-client/actions/workflows/build.yml)
[![PyPI - Version](https://img.shields.io/pypi/v/jupyter-kernel-client)](https://pypi.org/project/jupyter-kernel-client)

Jupyter Kernel Client to connect via WebSocket to Jupyter Servers.

## Requirements

- Jupyter Server with ipykernel running somewhere.
  You can install those packages using:

```sh
pip install jupyter-server ipykernel
```

## Install

To install the extension, execute:

```bash
pip install jupyter_kernel_client
```

## Usage

### Kernel Client

1. Start a Jupyter Server (or JupyterLab or Jupyter Notebook)

```sh
jupyter server
# ...
#    To access the server, open this file in a browser:
#        file:///home/echarles/.local/share/jupyter/runtime/jpserver-910631-open.html
#    Or copy and paste one of these URLs:
#        http://localhost:8888/?token=aed1fef59f754b9bfc99017e1dcf4d5602fc1a97d331069b
#        http://127.0.0.1:8888/?token=aed1fef59f754b9bfc99017e1dcf4d5602fc1a97d331069b
```

2. Note down the URL (usually `http://localhost:8888`) and the Server Token (in the above example it will be `aed1fef59f754b9bfc99017e1dcf4d5602fc1a97d331069b`)

3. Launch `python` in a terminal.

4. Execute the following snippet

```py
import os

from platform import node
from jupyter_kernel_client import KernelClient


with KernelClient(server_url="http://localhost:8888", token="aed1fef59f754b9bfc99017e1dcf4d5602fc1a97d331069b") as kernel:
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
```

### Jupyter Console

This package can be used to open a Jupyter Console to a Jupyter Kernel through HTTP 🐣.

1. Install the optional dependencies.

```sh
pip install jupyter-kernel-client[konsole]
```

2. Start a Jupyter Server (or JupyterLab or Jupyter Notebook).

```sh
jupyter server
# ...
#    To access the server, open this file in a browser:
#        file:///home/echarles/.local/share/jupyter/runtime/jpserver-910631-open.html
#    Or copy and paste one of these URLs:
#        http://localhost:8888/?token=aed1fef59f754b9bfc99017e1dcf4d5602fc1a97d331069b
#        http://127.0.0.1:8888/?token=aed1fef59f754b9bfc99017e1dcf4d5602fc1a97d331069b
```

3. Note down the URL (usually `http://localhost:8888`) and the Server Token (in the above example it will be `aed1fef59f754b9bfc99017e1dcf4d5602fc1a97d331069b`)

4. Start the console.

```sh
jupyter-konsole --url http://localhost:8888 --token aed1fef59f754b9bfc99017e1dcf4d5602fc1a97d331069b
```

Example of console session.

```bash
❯ jupyter-konsole --url http://localhost:8888 --token 0d2004a3f836e3dbb01a035c66a43b6fa06e44b004599835
[KonsoleApp] KernelHttpManager created a new kernel: ...
Jupyter Kernel console 0.2.0

Python 3.12.7 | packaged by conda-forge | (main, Oct  4 2024, 16:05:46) [GCC 13.3.0]
Type 'copyright', 'credits' or 'license' for more information
IPython 8.30.0 -- An enhanced Interactive Python. Type '?' for help.

In [1]: print("hello")
hello

In [2]:                                                                                                  
```

## Uninstall

To remove the extension, execute:

```bash
pip uninstall jupyter_kernel_client
```

## Contributing

### Development install

```bash
# Clone the repo to your local environment
# Change directory to the jupyter_kernel_client directory
# Install package in development mode - will automatically enable
# The server extension.
pip install -e ".[test,lint,typing]"
```

### Running Tests

Install dependencies:

```bash
pip install -e ".[test]"
```

To run the python tests, use:

```bash
pytest
```

### Development uninstall

```bash
pip uninstall jupyter_kernel_client
```

### Packaging the extension

See [RELEASE](RELEASE.md)
