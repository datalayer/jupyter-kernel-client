# Copyright (c) 2023-2024 Datalayer, Inc.
#
# BSD 3-Clause License

"""Kernel message de-/serializers.

Code copied from jupyter-server licensed under BSD 3-Clause License
Code source:
- https://github.com/jupyter-server/jupyter_server/blame/v2.12.0/jupyter_server/services/kernels/connection/base.py
- https://github.com/jupyter-server/jupyter_server/blame/v2.12.0/jupyter_server/utils.py
- https://github.com/jupyter-server/jupyter_server/blame/v2.12.0/jupyter_server/_tz.py
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone, tzinfo
import json
import logging
from typing import Any


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
    offsets: list[Any] = []
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


def serialize_msg_to_ws_default(msg):
    """Serialize a message using the default protocol."""
    offsets = []
    buffers = []

    msg_copy = dict(msg)
    msg_copy['header']['date'] = str(msg_copy['header']['date'])
    orig_buffers = msg_copy.pop("buffers", [])
    json_bytes = json.dumps(msg_copy).encode("utf-8")
    buffers.append(json_bytes)

    for b in orig_buffers:
        buffers.append(b)

    nbufs = len(buffers)
    offsets.append(4 * (nbufs + 1))

    for i in range(0, nbufs - 1):
        offsets.append(offsets[-1] + len(buffers[i]))

    total_size = offsets[-1] + len(buffers[-1])
    msg_buf = bytearray(total_size)

    msg_buf[0:4] = nbufs.to_bytes(4, byteorder="big")

    for i, off in enumerate(offsets):
        start = 4 * (i + 1)
        msg_buf[start:start+4] = off.to_bytes(4, byteorder="big")

    for i, b in enumerate(buffers):
        start = offsets[i]
        msg_buf[start:start+len(b)] = b

    return bytes(msg_buf)


def deserialize_msg_from_ws_default(ws_msg):
    """Deserialize a message using the default protocol."""
    if isinstance(ws_msg, str):
        return json.loads(ws_msg.encode('utf-8'))
    else:
        nbufs = int.from_bytes(ws_msg[:4], byteorder="big")
        offsets = []
        if nbufs < 2:
            raise ValueError("unsupported number of buffers")

        for i in range(nbufs):
            start = 4 * (i + 1)
            off = int.from_bytes(ws_msg[start:start+4], byteorder="big")
            offsets.append(off)

        json_start = offsets[0]
        json_stop = offsets[1]

        if not (0 <= json_start <= json_stop <= len(ws_msg)):
            raise ValueError("Invalid JSON offsets")

        json_bytes = ws_msg[json_start:json_stop]
        msg = json.loads(json_bytes.decode("utf-8"))
        msg["buffers"] = []
        for i in range(1, nbufs):
            start = offsets[i]
            stop = offsets[i+1] if (i+1) < len(offsets) else len(ws_msg)

            if not (0 <= start <= stop <= len(ws_msg)):
                raise ValueError(f"Invalid buffer offsets for chunk {i}")

            msg["buffers"].append(ws_msg[start:stop])

        return msg

def serialize_msg_to_ws_json(msg):
    """Serialize a default protocol with no buffers."""
    return json.dumps(msg, default=str)

def url_path_join(*pieces: str) -> str:
    """Join components of url into a relative url

    Use to prevent double slash when joining subpath. This will leave the
    initial and final / in place
    """
    initial = pieces[0].startswith("/")
    final = pieces[-1].endswith("/")
    stripped = [s.strip("/") for s in pieces]
    result = "/".join(s for s in stripped if s)
    if initial:
        result = "/" + result
    if final:
        result = result + "/"
    if result == "//":
        result = "/"
    return result


# constant for zero offset
ZERO = timedelta(0)


class tzUTC(tzinfo):  # noqa: N801
    """tzinfo object for UTC (zero offset)"""

    def utcoffset(self, d: datetime | None) -> timedelta:
        """Compute utcoffset."""
        return ZERO

    def dst(self, d: datetime | None) -> timedelta:
        """Compute dst."""
        return ZERO


def utcnow() -> datetime:
    """Return timezone-aware UTC timestamp"""
    return datetime.now(timezone.utc)


UTC = tzUTC()  # type:ignore[abstract]
