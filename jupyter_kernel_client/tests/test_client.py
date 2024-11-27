async def test_get(jp_fetch):
    await jp_fetch("jupyter-kernel-client/ping")

    assert False
