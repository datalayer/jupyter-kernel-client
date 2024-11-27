# Copyright (c) 2023-2024 Datalayer, Inc.
#
# BSD 3-Clause License

async def test_get(jp_fetch):
    await jp_fetch("jupyter-kernel-client/ping")

    assert False
