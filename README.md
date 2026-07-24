<!--
  ~ Copyright (c) 2023-2024 Datalayer, Inc.
  ~
  ~ BSD 3-Clause License
-->

[![Datalayer](https://assets.datalayer.tech/datalayer-25.svg)](https://datalayer.io)

[![Become a Sponsor](https://img.shields.io/static/v1?label=Become%20a%20Sponsor&message=%E2%9D%A4&logo=GitHub&style=flat&color=1ABC9C)](https://github.com/sponsors/datalayer)

# 🪐 Jupyter Kernel Client

> Jupyter Kernel Client through HTTP and WebSocket

[![Github Actions Status](https://github.com/datalayer/jupyter-kernel-client/workflows/Build/badge.svg)](https://github.com/datalayer/jupyter-kernel-client/actions/workflows/build.yml)
[![PyPI - Version](https://img.shields.io/pypi/v/jupyter-kernel-client)](https://pypi.org/project/jupyter-kernel-client)

`Jupyter Kernel Client` allows you to connect to live Jupyter Kernels through HTTP and WebSocket.

> A `Kernel` is the process responsible to execute the notebook code.

`Jupyter Kernel Client` also provides a easy to use interactive Konsole (console for **K**ernels aka REPL, Read-Evaluate-Print-Loop).

To install the library, run the following command.

```bash
pip install jupyter_kernel_client
```

## Jupyter Server

Check you have a Jupyter Server with ipykernel running somewhere. You can install those packages with the following command.

```bash
pip install jupyter-server ipykernel
```

1. Start a Jupyter Server.

```bash
# make jupyter-server
jupyter server --port 8888 --ServerApp.port_retries 0 --IdentityProvider.token MY_TOKEN
```

2. Launch a IPython REPL in a terminal with `ipython` (or `jupyter console`). Execute the following snippet (update the server_url and token if needed).

```py
import os

from platform import node
from jupyter_kernel_client import KernelClient

with KernelClient(server_url="http://localhost:8888", token="MY_TOKEN") as kernel:
    code = """import os
from platform import node
print(f"Hey {os.environ.get('USER', 'John Smith')} from {node()}.")
"""
    reply = kernel.execute(code)
    print(reply)
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

Check the response.

```json
{"execution_count": 1, "outputs": [{"output_type": "stream", "name": "stdout", "text": "Hey echarles from eric.\n"}], "status": "ok"}
```

Instead of using the kernel client as context manager, you can call the `start()` and `stop()` methods.

```py
from jupyter_kernel_client import KernelClient

kernel = KernelClient(server_url="http://localhost:8888", token="MY_TOKEN")
kernel.start()
reply = kernel.execute(code)
print(reply)
kernel.stop()
```

To connect to an existing Jupyter Kernel, first start JupyterLab, open a Notebook with a Kernel and take not of the `Kernel ID`.

> TODO: Document how to get the `Kernel ID`.

```bash
make jupyterlab
```

You can now connect to the existing Kernel and run code (do not invoke `stop`).

```py
from jupyter_kernel_client import KernelClient

kernel = KernelClient(server_url="http://localhost:8888", kernel_id="83ef59b7-9c78-40bd-8cc2-4447635e7d0b", token="MY_TOKEN")
kernel.start()
reply = kernel.execute("x=1")
print(reply)
```

## Kaggle Kernel

Kaggle supports both batch execution and interactive kernel connections from code.

- Detailed guide: [Kaggle docs](docs/docs/kaggle.mdx)
- Includes auth modes, channels URL retrieval, explicit and parsed connection
  options, batch execution from zero, accelerator matrix, and operational notes.

Quick batch example:

```py
from jupyter_kernel_client import KaggleKernelExecutor

executor = KaggleKernelExecutor()
result = executor.execute(
    "print('hello from kaggle')",
    title="jkc-demo",
#    accelerator="NvidiaTeslaT4",
    wait=True,
)
print(result)
print(result.status)
print(result.stdout)
print(result.kernel_reply)
print(result.to_kernel_reply())
```

`KaggleExecutionResult` includes normalized helpers:

- `stdout` / `stderr` convenience properties
- `kernel_reply` (same normalized Jupyter-like payload as `to_kernel_reply()`)
- auto-generated notebook cell IDs in batch submissions to match modern notebook metadata expectations

Quick interactive example:

```py
from jupyter_kernel_client import KaggleKernelClient

channels_url = (
    "wss://kkb-production.jupyter-proxy.kaggle.net/k/12345678/eyJhbGci.../proxy"
    "/api/kernels/11e073f0-e82d-4029-be8d-3918f7ed1a9e/channels?session_id=..."
)

with KaggleKernelClient.from_channels_url(channels_url, token=None) as kernel:
    reply = kernel.execute("x = 1 + 1; print(x)")
    print(reply)
```

## Google Colab Kernel

Google Colab exposes a Jupyter-compatible kernel behind an authenticating proxy.
Use `ColabKernelClient` to connect to an already-running Colab runtime.

- Detailed guide: [Google Colab docs](docs/docs/google-colab.mdx)
- Includes explicit-value mode, channels URL mode, parser helpers, auth behavior,
  and channels URL retrieval steps.

Quick example:

```py
from jupyter_kernel_client import ColabKernelClient

channels_url = (
    "wss://<colab-host>/api/kernels/<kernel_id>/channels"
    "?session_id=<...>&colab-runtime-proxy-token=<proxy_token>&colab-client-agent=web"
)

with ColabKernelClient.from_channels_url(channels_url) as kernel:
    reply = kernel.execute("x = 1 + 1; print(x)")
    print(reply)
```

### Jupyter Konsole aka Console for Kernels

This package can be used to open a Jupyter Console to a Jupyter Kernel 🐣.

1. Install the optional dependencies.

```bash
pip install jupyter-kernel-client[konsole]
```

2. Start a Jupyter Server.

```bash
# make jupyter-server
jupyter server --port 8888 --ServerApp.port_retries 0 --IdentityProvider.token MY_TOKEN
```

3. Start the konsole and execute code.

```bash
# make jupyter-konsole
jupyter konsole --url http://localhost:8888 --token MY_TOKEN
```

```bash
[KonsoleApp] KernelHttpManager created a new kernel:...
Jupyter Konsole...

In [1]: 1+1
2
```

## Uninstall

To remove the library, execute the following command.

```bash
pip uninstall jupyter_kernel_client
```

## Contributing

### Development install

```bash
# Clone the repo to your local environment
# Change directory to the jupyter_kernel_client directory
# Install package in development mode, this will automatically enable the server extension.
pip install -e ".[konsole,test,lint,typing]"
```

### Running Tests

Install dependencies.

```bash
pip install -e ".[test]"
```

Run the python tests.

```bash
pytest
```

### Development uninstall

```bash
pip uninstall jupyter_kernel_client
```

### Packaging the library

See [RELEASE](RELEASE.md)
