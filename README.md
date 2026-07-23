<!--
  ~ Copyright (c) 2023-2024 Datalayer, Inc.
  ~
  ~ BSD 3-Clause License
-->

[![Datalayer](https://assets.datalayer.tech/datalayer-25.svg)](https://datalayer.io)

[![Become a Sponsor](https://img.shields.io/static/v1?label=Become%20a%20Sponsor&message=%E2%9D%A4&logo=GitHub&style=flat&color=1ABC9C)](https://github.com/sponsors/datalayer)

# 🪐 Jupyter Kernel Client through HTTP and WebSocket

[![Github Actions Status](https://github.com/datalayer/jupyter-kernel-client/workflows/Build/badge.svg)](https://github.com/datalayer/jupyter-kernel-client/actions/workflows/build.yml)
[![PyPI - Version](https://img.shields.io/pypi/v/jupyter-kernel-client)](https://pypi.org/project/jupyter-kernel-client)

`Jupyter Kernel Client` allows you to connect to live Jupyter Kernels through HTTP and WebSocket.

> A `Kernel` is the process responsible to execute the notebook code.

`Jupyter Kernel Client` also provides a easy to use interactive Konsole (console for **K**ernels aka REPL, Read-Evaluate-Print-Loop).

To install the library, run the following command.

```bash
pip install jupyter_kernel_client
```

## Usage

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

## Connect to an existing Kernel

First start JupyterLab, open a Notebook with a Kernel and take not of the `Kernel ID`.

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

## Connect to a Google Colab Kernel

Google Colab exposes a Jupyter-compatible kernel behind an authenticating proxy.
Use `ColabKernelClient` to connect to it. You obtain the `server_url`,
`kernel_id`, and `proxy_token` from Colab's runtime assignment API.

```py
from jupyter_kernel_client import ColabKernelClient

kernel = ColabKernelClient(
    server_url="https://<colab-host>",
    kernel_id="<kernel_id>",
    proxy_token="<proxy_token>",
)
kernel.start()
reply = kernel.execute("x = 1")
print(reply)
# Do not shut down the Colab kernel; disconnect only.
kernel.stop(shutdown_kernel=False)
```

`ColabKernelClient` forwards the proxy token both as the
`X-Colab-Runtime-Proxy-Token` header and the `colab-runtime-proxy-token`
WebSocket query parameter, which the Colab proxy requires for authentication.

### How to obtain the Colab connection info

The three values (`server_url`, `kernel_id`, `proxy_token`) are the pieces of the
WebSocket URL that Colab's own frontend uses to reach your assigned runtime:

```
wss://<host>/api/kernels/<kernel_id>/channels?session_id=<...>&colab-runtime-proxy-token=<proxy_token>&colab-client-agent=web
```

For example:

```
wss://<colab-host>/api/kernels/<kernel_id>/channels?session_id=<session_id>&colab-runtime-proxy-token=<proxy_token>&colab-client-agent=web
```

They are tied to **your** Colab session and are short-lived — they change whenever
the runtime is reassigned or reconnected, so re-fetch them after reconnecting.

The easiest way to read them is through your browser's developer tools:

1. Open your notebook on [colab.research.google.com](https://colab.research.google.com)
   and **connect to a runtime** (*Runtime → Connect*, or run any cell).
2. Open DevTools (`F12`) → **Network** tab and select the **WS** filter (or type
   `kernels` in the filter box).
3. Run a cell to trigger kernel traffic.
4. Click the `.../api/kernels/<kernel_id>/channels?...` request and read off:
   - **`server_url`** — the scheme + host *before* `/api/kernels` (change the
    `wss://` scheme to `https://`). Colab assigns a per-session host such as
    `https://<colab-host>.prod.colab.dev`;
     there is usually **no** `/tun/m/...` path segment.
   - **`kernel_id`** — the UUID segment right after `/api/kernels/`.
   - **`proxy_token`** — the `colab-runtime-proxy-token` query parameter (this is
     the same value as the `X-Colab-Runtime-Proxy-Token` request header). Ignore
     the `session_id` and `colab-client-agent` query parameters.

> The programmatic "runtime assignment API" is the internal endpoint the Colab
> frontend calls (authenticated with your Google session); it is not an officially
> published public API, so the DevTools method above is the practical way to
> obtain the values.

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
