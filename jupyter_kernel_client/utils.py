# Copyright (c) 2023-2024 Datalayer, Inc.
#
# BSD 3-Clause License

"""Kernel message de-/serializers.

Code copied from jupyter-server licensed under BSD 3-Clause License
Code source: https://github.com/jupyter-server/jupyter_server/blame/v2.12.0/jupyter_server/services/kernels/connection/base.py
"""

from typing import Any, List


def serialize_msg_to_ws_v1(msg_or_list, channel, pack=None):
    """Serialize a message using the v1 protocol."""
    if pack:
        msg_list = [
            pack(msg_or_list["header"]),
            pack(msg_or_list["parent_header"]),
            pack(msg_or_list["metadata"]),
            pack(msg_or_list["content"]),
        ]
    else:
        msg_list = msg_or_list
    channel = channel.encode("utf-8")
    offsets: List[Any] = []
    offsets.append(8 * (1 + 1 + len(msg_list) + 1))
    offsets.append(len(channel) + offsets[-1])
    for msg in msg_list:
        offsets.append(len(msg) + offsets[-1])
    offset_number = len(offsets).to_bytes(8, byteorder="little")
    offsets = [offset.to_bytes(8, byteorder="little") for offset in offsets]
    bin_msg = b"".join([offset_number, *offsets, channel, *msg_list])
    return bin_msg


def deserialize_msg_from_ws_v1(ws_msg):
    """Deserialize a message using the v1 protocol."""
    offset_number = int.from_bytes(ws_msg[:8], "little")
    offsets = [
        int.from_bytes(ws_msg[8 * (i + 1) : 8 * (i + 2)], "little") for i in range(offset_number)
    ]
    channel = ws_msg[offsets[0] : offsets[1]].decode("utf-8")
    msg_list = [ws_msg[offsets[i] : offsets[i + 1]] for i in range(1, offset_number - 1)]
    return channel, msg_list
