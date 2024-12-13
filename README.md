<!--
  ~ Copyright (c) 2023-2024 Datalayer, Inc.
  ~
  ~ BSD 3-Clause License
-->

[![Datalayer](https://assets.datalayer.tech/datalayer-25.svg)](https://datalayer.io)

[![Become a Sponsor](https://img.shields.io/static/v1?label=Become%20a%20Sponsor&message=%E2%9D%A4&logo=GitHub&style=flat&color=1ABC9C)](https://github.com/sponsors/datalayer)

# Jupyter Kernel Client (via WebSocket and HTTP)

[![Github Actions Status](https://github.com/datalayer/jupyter-kernel-client/workflows/Build/badge.svg)](https://github.com/datalayer/jupyter-kernel-client/actions/workflows/build.yml)
[![PyPI - Version](https://img.shields.io/pypi/v/jupyter-kernel-client)](https://pypi.org/project/jupyter-kernel-client)

Jupyter Kernel Client allows you to connect via WebSocket and HTTP to Jupyter Kernels. It also provide a easy to use interactive Konsole (console for **K**ernels).

To install the library, run the following command.

```sh
pip install jupyter_kernel_client
```

## Usage

Check you have a Jupyter Server with ipykernel running somewhere. You can install those packages using:

```sh
pip install jupyter-server ipykernel
```

### Kernel Client

1. Start a Jupyter Server.

```sh
jupyter server --port 8888 --IdentityProvider.token MY_TOKEN
```

2. Launch `python` in a terminal and execute the following snippet (update the server_url and token).

```py
import os

from platform import node
from jupyter_kernel_client import KernelClient


with KernelClient(server_url="http://localhost:8888", token="MY_TOKEN") as kernel:
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

### Jupyter Konsole (aka Console for Kernels)

This package can be used to open a Jupyter Console to a Jupyter Kernel 🐣.

1. Install the optional dependencies.

```sh
pip install jupyter-kernel-client[konsole]
```

2. Start a Jupyter Server.

```sh
jupyter server --port 8888 --IdentityProvider.token MY_TOKEN
```

3. Start the konsole and execute code.

```sh
jupyter konsole --url http://localhost:8888 --token MY_TOKEN
```

```sh
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

To remove the library, execute:

```sh
pip uninstall jupyter_kernel_client
```

## Contributing

### Development install

```sh
# Clone the repo to your local environment
# Change directory to the jupyter_kernel_client directory
# Install package in development mode - will automatically enable
# The server extension.
pip install -e ".[konsole,test,lint,typing]"
```

### Running Tests

Install dependencies:

```sh
pip install -e ".[test]"
```

To run the python tests, use:

```sh
pytest
```

### Development uninstall

```sh
pip uninstall jupyter_kernel_client
```

### Packaging the library

See [RELEASE](RELEASE.md)
