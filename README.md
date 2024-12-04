# Jupyter Kernel Client (through http)

[![Github Actions Status](https://github.com/datalayer/jupyter-kernel-client/workflows/Build/badge.svg)](https://github.com/datalayer/jupyter-kernel-client/actions/workflows/build.yml)

Jupyter Kernel Client to connect via WebSocket to Jupyter Servers.

## Requirements

- Jupyter Server

## Install

To install the extension, execute:

```bash
pip install jupyter_kernel_client
```

## Usage

1. Start a jupyter server (or JupyterLab or Jupyter Notbook)

```sh
jupyter server
```

1. Note down the URL (usually `http://localhost:8888`) and the server token

1. Open a Python terminal

1. Execute the following snippet

```py
import os
from platform import node
from jupyter_kernel_client import KernelClient

with KernelClient(server_url="http://localhost:8888", token="...") as kernel:
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

## Uninstall

To remove the extension, execute:

```bash
pip uninstall jupyter_kernel_client
```

## Troubleshoot

If you are seeing the frontend extension, but it is not working, check
that the server extension is enabled:

```bash
jupyter server extension list
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
