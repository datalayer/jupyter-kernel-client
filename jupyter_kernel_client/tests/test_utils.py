# Copyright (c) 2023-2024 Datalayer, Inc.
# Copyright (c) 2025      Google
#
# BSD 3-Clause License

import json
from jupyter_kernel_client.utils import serialize_msg_to_ws_json, serialize_msg_to_ws_default, deserialize_msg_from_ws_default, serialize_msg_to_ws_v1, deserialize_msg_from_ws_v1

def test_serialize_msg_to_ws_json():
    src_msg = {
        "header": {
            "msg_id": "c0a8012e-1f3b-4c3a-9c77-123456789abc",
            "username": "test-user",
            "session": "1c2d3e4f-aaaa-bbbb-cccc-0123456789ab",
            "date": "2026-01-26T12:34:56.789Z",
            "msg_type": "execute_request",
            "version": "5.3",
        },
        "parent_header": {},
        "metadata": {},
        "content": {
            "code": "print('hello world')",
            "silent": False,
            "store_history": True,
            "user_expressions": {},
            "allow_stdin": True,
            "stop_on_error": True,
        },
        "buffers": [],
    }

    expected_output = json.dumps(src_msg)
    serialized_msg = serialize_msg_to_ws_json(src_msg)
    assert expected_output == serialized_msg

def test_serialize_and_deserialize_msg_to_ws_default():
    src_msg = {
        "header": {
            "msg_id": "7f3b9d8d-2c6c-4b71-9b64-111111111111",
            "username": "test-user",
            "session": "1c2d3e4f-aaaa-bbbb-cccc-0123456789ab",
            "date": "2026-01-26T12:35:10.123Z",
            "msg_type": "comm_msg",
            "version": "5.3",
        },
        "parent_header": {},
        "metadata": {
            "buffer_paths": [
                ["content", "data", "payload"],
                ["content", "data", "extra_blob"]
            ]
        },
        "content": {
            "comm_id": "abc123abc123abc123abc123abc123ab",
            "target_name": "my_binary_comm",
            "data": {
                "dtype": "uint8",
                "shape": [4],
                "payload": None,
                "extra_blob": None,
                "note": "payload + extra_blob come from buffers",
            },
        },
        "buffers": [
            b"\x01\x02\x03\x04",
            b"\xde\xad\xbe\xef\x00\xff",
        ],
    }

    serialized_msg = serialize_msg_to_ws_default(src_msg)
    bufn = int.from_bytes(serialized_msg[0:4], byteorder="big")
    buffers = src_msg['buffers'] or []

    for i in range(1, bufn):
        # ignore the json message for now, it's tested the deserialized msg
        start = (i+1) * 4
        offset = int.from_bytes(serialized_msg[start:start+4], byteorder="big")
        buf = buffers[i-1]
        serialized_buf_val = serialized_msg[offset:offset+len(buf)]
        assert serialized_buf_val == buf

    deserialized_msg = deserialize_msg_from_ws_default(serialized_msg)
    assert deserialized_msg == src_msg

def test_serialize_and_deserialize_msg_to_ws_v1():
    def pack(obj) -> bytes:
        return json.dumps(obj, separators=(",", ":"), sort_keys=True).encode("utf-8")

    src_msg = {
        "channel": "shell",
        "header": {
            "msg_id": "7f3b9d8d-2c6c-4b71-9b64-111111111111",
            "username": "test-user",
            "session": "1c2d3e4f-aaaa-bbbb-cccc-0123456789ab",
            "date": "2026-01-26T12:35:10.123Z",
            "msg_type": "comm_msg",
            "version": "5.3",
        },
        "parent_header": {},
        "metadata": {
            "buffer_paths": [
                ["content", "data", "payload"],
                ["content", "data", "extra_blob"]
            ]
        },
        "content": {
            "comm_id": "abc123abc123abc123abc123abc123ab",
            "target_name": "my_binary_comm",
            "data": {
                "dtype": "uint8",
                "shape": [4],
                "payload": None,
                "extra_blob": None,
                "note": "payload + extra_blob come from buffers",
            },
        },
        "buffers": [
            b"\x01\x02\x03\x04",
            b"\xde\xad\xbe\xef\x00\xff",
        ],
    }

    serialized_msg = serialize_msg_to_ws_v1(src_msg, channel="shell", pack=pack)
    # construct the msg lists for the serialized msg
    offset = int.from_bytes(serialized_msg[:8], byteorder="little")
    offsets = [
        int.from_bytes(serialized_msg[8 * (i + 1) : 8 * (i + 2)], byteorder="little") for i in range(offset)
    ]
    serialized_list = [serialized_msg[offsets[i]:offsets[i+1]] for i in range(1, offset-1)]

    _, deserialized_msg = deserialize_msg_from_ws_v1(serialized_msg)
    assert serialized_list == deserialized_msg

