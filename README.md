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
Use `ColabKernelClient` to connect to a kernel that is **already running** on a
Colab runtime.

> **Note:** this client only *reuses an existing* Colab kernel — it does not
> create a Colab runtime from scratch. Consumer Colab has no public API to
> provision a runtime from a standalone process (authentication lives in your
> browser session). Start a runtime from the Colab UI first (*Runtime → Connect*,
> or run any cell), then connect to it here.

You need three values — `server_url`, `kernel_id`, and `proxy_token` — which are
all present in the WebSocket **channels** URL that Colab's own frontend uses (see
[How to obtain the Colab channels URL](#how-to-obtain-the-colab-channels-url)).

### Option A: connect with explicit values

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

### Option B: connect from the channels URL

Copy the WebSocket **channels** URL from your browser and let the client parse
the `server_url`, `kernel_id` and `proxy_token` out of it:

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

You can also derive the values yourself with `parse_colab_channels_url`:

```py
from jupyter_kernel_client import parse_colab_channels_url

server_url, kernel_id, proxy_token = parse_colab_channels_url(channels_url)
```

`ColabKernelClient` forwards the proxy token both as the
`X-Colab-Runtime-Proxy-Token` header and the `colab-runtime-proxy-token`
WebSocket query parameter, which the Colab proxy requires for authentication.


### How to obtain the Colab channels URL

The three values (`server_url`, `kernel_id`, `proxy_token`) all live in the
WebSocket **channels** URL that Colab's own frontend uses to reach your assigned
runtime:

```
wss://<host>/api/kernels/<kernel_id>/channels?session_id=<...>&colab-runtime-proxy-token=<proxy_token>&colab-client-agent=web
```

They are tied to **your** Colab session and are short-lived — they change whenever
the runtime is reassigned or reconnected, so re-fetch them after reconnecting.

Read them through your browser's developer tools:

1. Open your notebook on [colab.research.google.com](https://colab.research.google.com)
   and **connect to a runtime** (*Runtime → Connect*, or run any cell).
2. Open DevTools (`F12`) → **Network** tab and select the **WS** filter (or type
   `kernels` in the filter box).
3. Run a cell to trigger kernel traffic.
4. Click the `.../api/kernels/<kernel_id>/channels?...` request and copy the whole
   URL — pass it to `ColabKernelClient.from_channels_url(...)`. If you prefer to
   read the parts by hand:
   - **`server_url`** — the scheme + host *before* `/api/kernels` (change the
     `wss://` scheme to `https://`), e.g. `https://<colab-host>.prod.colab.dev`.
   - **`kernel_id`** — the UUID segment right after `/api/kernels/`.
   - **`proxy_token`** — the `colab-runtime-proxy-token` query parameter.

> **Why can't this be done "from zero" with a credential?** For consumer Colab,
> there is no official public API, SDK, or API key to create or assign a
> [colab.research.google.com](https://colab.research.google.com) runtime from a
> standalone process — Colab's
> [FAQ](https://research.google.com/colaboratory/faq.html) disallows driving
> runtimes outside the notebook UI. Start the runtime in the browser, then
> connect with the channels URL above. For a true programmatic "from zero" flow,
> use [Colab Enterprise](https://docs.cloud.google.com/colab/docs/runtimes) on
> Google Cloud (provisioned with Google Cloud credentials), which is out of scope
> for `jupyter-kernel-client`.

## Connect to a Kaggle Kernel

Kaggle notebooks expose a Jupyter-compatible kernel behind an authenticating
proxy. `KaggleKernelClient` supports two authentication modes:

- **API token (default).** Provide a Kaggle API token, either explicitly through
  the `token` argument or via the `KAGGLE_API_TOKEN` environment variable. The
  token authenticates REST/WebSocket requests, so omitting `kernel_id` lets the
  client **create** a new kernel on the runtime (`POST /api/kernels`).
- **Signed proxy URL.** When connecting to an already-running notebook session,
  the signed JWT embedded in the proxied `server_url` path carries the
  authentication and no token is required (pass `token=None`).

### Option A: create a kernel with an API token

Set the `KAGGLE_API_TOKEN` environment variable (or pass `token=...`) and omit
`kernel_id` to create a fresh kernel:

```py
import os
from jupyter_kernel_client import KaggleKernelClient

os.environ["KAGGLE_API_TOKEN"] = "..."  # or export it in your shell

with KaggleKernelClient(
    server_url="https://kkb-production.jupyter-proxy.kaggle.net/k/12345678/eyJhbGci.../proxy",
) as kernel:
    print("kernel_id:", kernel.id)  # a new kernel was created
    reply = kernel.execute("x = 1 + 1; print(x)")
    print(reply)
```

### Option B: connect from the channels URL

To connect to an already-running session, copy the WebSocket **channels** URL and
let the client parse it (the JWT in the URL provides the authentication, so no
token is needed):

```py
from jupyter_kernel_client import KaggleKernelClient

channels_url = (
    "wss://kkb-production.jupyter-proxy.kaggle.net/k/12345678/eyJhbGci.../proxy"
    "/api/kernels/11e073f0-e82d-4029-be8d-3918f7ed1a9e/channels?session_id=..."
)

with KaggleKernelClient.from_channels_url(channels_url, token=None) as kernel:
    print("kernel_id:", kernel.id)
    reply = kernel.execute("x = 1 + 1; print(x)")
    print(reply)
```

### Option C: connect with an explicit server URL and kernel id

If you already have the `server_url` (the HTTP(S) base ending in `/proxy`) and
`kernel_id`, pass them directly:

```py
from jupyter_kernel_client import KaggleKernelClient

kernel = KaggleKernelClient(
    server_url="https://kkb-production.jupyter-proxy.kaggle.net/k/12345678/eyJhbGci.../proxy",
    kernel_id="11e073f0-e82d-4029-be8d-3918f7ed1a9e",
)
kernel.start()
reply = kernel.execute("x = 1")
print(reply)
# Do not shut down the Kaggle kernel; disconnect only.
kernel.stop(shutdown_kernel=False)
```

You can also derive the two values yourself with `parse_kaggle_channels_url`:

```py
from jupyter_kernel_client import parse_kaggle_channels_url

server_url, kernel_id = parse_kaggle_channels_url(channels_url)
```

### How to obtain the Kaggle channels URL

When connecting to an existing session (Option B/C), the `server_url` /
`kernel_id` come from an **active browser session**. The official Kaggle API
(`kaggle` CLI / `kagglehub`) only exposes *batch* kernel operations
(push/pull/status/output) for running notebooks as jobs. To read the channels
URL:

1. Open your notebook on [kaggle.com](https://www.kaggle.com) and start a session
   (run any cell).
2. Open DevTools (`F12`) → **Network** tab, select the **WS** filter (or type
   `channels` in the filter box).
3. Run a cell to trigger kernel traffic.
4. Click the `.../proxy/api/kernels/<kernel_id>/channels?...` request and copy its
   URL. The signed JWT in the `/k/<n>/<jwt>/proxy` path segment carries the
   authentication. These values are tied to **your** session and are short-lived
   — re-fetch them after reconnecting.

### Run code "from zero" with the batch API

Unlike consumer Colab, Kaggle has an **official public API** that can create and
run a notebook from scratch — no browser session required. `KaggleKernelExecutor`
wraps that batch API (`kernels_push` → status polling → output download), so you
can execute code against a fresh Kaggle kernel programmatically.

Install the optional dependency and authenticate:

```bash
pip install 'jupyter-kernel-client[kaggle]'
```

Provide Kaggle API credentials the same way the `kaggle` CLI does — either a
`~/.kaggle/kaggle.json` file (from *Account → Create New API Token*) or the
`KAGGLE_API_TOKEN` environment variables.

```py
from jupyter_kernel_client import KaggleKernelExecutor

executor = KaggleKernelExecutor()  # username read from kaggle.json / env

result = executor.execute(
    "print('hello from kaggle')",
    title="jkc-demo",
  accelerator="NvidiaTeslaT4",  # or "T4" / "P100"
    enable_internet=True,
    wait=True,          # block until the kernel finishes
    timeout=3600,       # seconds
    download_output=True,
)

print(result.status)        # e.g. "complete" or "error"
print(result.succeeded)     # True when status == complete
print(result.url)           # kaggle.com URL of the pushed kernel
print(result.log)           # captured execution log (if downloaded)
print(result.output_files)  # paths to downloaded output artifacts
```

Each run is a **batch job**: the code is pushed as a notebook (or a `script.py`
when `kernel_type="script"`), queued, executed on Kaggle's infrastructure, and
its output is downloaded when it reaches a terminal state
(`complete` / `error` / `cancel_acknowledged`). Useful knobs on `execute(...)`:

- `slug` / `title` — the kernel identifier and display title (a slug is derived
  from the title when omitted).
- `accelerator` — Kaggle accelerator value (`NvidiaTeslaP100`, `NvidiaTeslaT4`,
  `NvidiaTeslaT4Highmem`, `NvidiaL4`, `NvidiaL4X1`, `NvidiaTeslaA100`,
  `NvidiaH100`, `NvidiaRtxPro6000`). Friendly aliases such as `P100`, `T4`,
  `A100`, and `H100` are accepted.
- `enable_gpu`, `enable_internet`, `is_private` — kernel resources and
  visibility.
- `dataset_sources`, `competition_sources`, `kernel_sources`, `model_sources` —
  attach Kaggle data sources.
- `wait=False` — push and return immediately; poll later with
  `executor.status(slug)` and fetch artifacts with `executor.output(slug, dest)`.

> Note: Kaggle free-tier availability usually includes `P100` and `T4`.
> Accelerators such as `A100`, `H100`, and `L4` are often restricted to specific
> competitions or internal Kaggle workloads.

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
