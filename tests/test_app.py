import asyncio

import httpx
from fastapi import FastAPI

from yt_live_list.app import create_app
from yt_live_list.models import Broadcast
from yt_live_list.youtube import YouTubeError


class FakeSource:
    def __init__(self, broadcasts: list[Broadcast] | None = None) -> None:
        self.broadcasts = broadcasts or []
        self.error = False
        self.calls = 0

    def list_broadcasts(self) -> list[Broadcast]:
        self.calls += 1
        if self.error:
            raise YouTubeError('failed')
        return self.broadcasts


def request(app: FastAPI, path: str) -> httpx.Response:
    async def send() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url='http://testserver',
        ) as client:
            return await client.get(path)

    return asyncio.run(send())


def test_index_renders_broadcast(sample_broadcast: Broadcast) -> None:
    source = FakeSource([sample_broadcast])
    app = create_app(source=source, cache_ttl_seconds=60)

    response = request(app, '/')

    assert response.status_code == 200
    assert 'Game night' in response.text
    assert 'https://www.youtube.com/watch?v=abc123' in response.text
    assert 'Live now' in response.text


def test_index_renders_empty_state() -> None:
    app = create_app(source=FakeSource(), cache_ttl_seconds=60)

    response = request(app, '/')

    assert response.status_code == 200
    assert 'No streams yet' in response.text


def test_index_returns_503_on_initial_api_error() -> None:
    source = FakeSource()
    source.error = True
    app = create_app(source=source, cache_ttl_seconds=60)

    response = request(app, '/')

    assert response.status_code == 503
    assert 'Couldn’t load the streams' in response.text


def test_health_check_does_not_call_source() -> None:
    source = FakeSource()
    app = create_app(source=source, cache_ttl_seconds=60)

    response = request(app, '/healthz')

    assert response.status_code == 200
    assert response.json() == {'status': 'ok'}
    assert source.calls == 0
