
# Copyright (c) 2023-2024 Datalayer, Inc.
# Copyright (c) 2025      Google
#
# BSD 3-Clause License

from jupyter_kernel_client.manager import KernelHttpManager
from jupyter_kernel_client import KernelClient


def test_list_kernels(jupyter_server):
    port, token = jupyter_server

    # Start a kernel to ensure the list is not empty
    with KernelClient(server_url=f"http://localhost:{port}", token=token) as kernel:
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

