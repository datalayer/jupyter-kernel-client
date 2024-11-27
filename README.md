# Jupyter Kernel Client (through websocket)

[![Github Actions Status](https://github.com/datalayer/jupyter_kernel_client/workflows/Build/badge.svg)](https://github.com/datalayer/jupyter_kernel_client/actions/workflows/build.yml)

Jupyter Kernel Client to connect via WebSocket to Jupyter Servers.

## Requirements

- Jupyter Server

## Install

To install the extension, execute:

```bash
pip install jupyter_kernel_client
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

# To test a specific file
pytest jupyter_kernel_client/tests/test_handlers.py

# To run a specific test
pytest jupyter_kernel_client/tests/test_handlers.py -k "test_get"
```

### Development uninstall

```bash
pip uninstall jupyter_kernel_client
```

### Packaging the extension

See [RELEASE](RELEASE.md)
