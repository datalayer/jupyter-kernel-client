# Copyright (c) 2023-2024 Datalayer, Inc.
#
# BSD 3-Clause License

import os
from platform import node
from threading import Event, Thread

from jupyter_kernel_client import KernelClient


# def test_basic_usage(jp_serverapp):
#     def _run(server_url, token, event):
#         with KernelClient(server_url=server_url, token=token) as kernel:
#             reply = kernel.execute(
#                 """import os
#         from platform import node
#         print(f"Hey {os.environ.get('USER', 'John Smith')} from {node()}.")
#         """
#             )

#             assert reply["execution_count"] == 1
#             assert reply["outputs"] == [
#                 {
#                     "output_type": "stream",
#                     "name": "stdout",
#                     "text": f"Hey {os.environ.get('USER', 'John Smith')} from {node()}.\n",
#                 }
#             ]
#             assert reply["status"] == "ok"

#         event.set()

#     done = Event()
#     t = Thread(
#         target=_run,
#         kwargs={
#             "server_url": jp_serverapp.connection_url,
#             "token": jp_serverapp.identity_provider.token,
#             "event": done
#         },
#     )
#     t.start()
#     done.wait(5)

#     t.join(5)
