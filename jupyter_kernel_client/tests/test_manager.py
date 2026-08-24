
# Copyright (c) 2023-2024 Datalayer, Inc.
# Copyright (c) 2025      Google
#
# BSD 3-Clause License

from jupyter_kernel_client.manager import KernelHttpManager, fetch
from jupyter_kernel_client import JupyterKernelClient


def test_fetch_preserves_provider_authorization_and_queries_jupyter_token(monkeypatch):
    captured = {}

    class Response:
        def raise_for_status(self):
            return None

    def get(url, **kwargs):
        captured.update(url=url, **kwargs)
        return Response()

    monkeypatch.setattr("jupyter_kernel_client.manager.requests.get", get)

    fetch(
        "https://provider.example/api/kernels",
        token="jupyter-token",
        headers={"Authorization": "Bearer provider-token"},
    )

    assert captured["headers"]["Authorization"] == "Bearer provider-token"
    assert captured["params"]["token"] == "jupyter-token"


def test_list_kernels(jupyter_server):
    port, token = jupyter_server

    # Start a kernel to ensure the list is not empty
    with JupyterKernelClient(server_url=f"http://localhost:{port}", token=token) as kernel:
        kernel_id = kernel.id
        # The manager is created after the kernel is started to ensure we can list it.
        manager = KernelHttpManager(server_url=f"http://localhost:{port}", token=token)
        kernels = manager.list_kernels()

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
