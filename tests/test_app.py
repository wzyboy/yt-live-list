import asyncio
from datetime import UTC
from datetime import datetime
from datetime import timedelta

import httpx
from fastapi import FastAPI

from yt_live_list.app import create_app
from yt_live_list.app import format_duration
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
    assert 'href="./static/style.css"' in response.text
    assert 'class="refresh" href="./"' in response.text
    assert 'class="cache-time"' in response.text


def test_index_renders_duration_and_end_time() -> None:
    broadcast = Broadcast(
        video_id='completed',
        title='Completed stream',
        status='completed',
        starts_at=datetime(2026, 7, 13, 18, tzinfo=UTC),
        thumbnail_url=None,
        privacy_status='unlisted',
        ends_at=datetime(2026, 7, 13, 20, 30, tzinfo=UTC),
    )
    app = create_app(source=FakeSource([broadcast]), cache_ttl_seconds=60)

    response = request(app, '/')

    assert response.status_code == 200
    assert '>2h 30m</span>' in response.text
    assert 'data-end-time="2026-07-13T20:30:00+00:00"' in response.text
    assert 'title="Ended 2026-07-13 20:30 UTC"' in response.text


def test_format_duration() -> None:
    assert format_duration(timedelta(seconds=30)) == '<1m'
    assert format_duration(timedelta(hours=2, minutes=5)) == '2h 5m'
    assert format_duration(timedelta(days=1, hours=3)) == '1d 3h'


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
