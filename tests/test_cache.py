from datetime import UTC
from datetime import datetime

import pytest

from yt_live_list.cache import BroadcastCache
from yt_live_list.models import Broadcast
from yt_live_list.youtube import YouTubeError


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_cache_reuses_fresh_result(sample_broadcast: Broadcast) -> None:
    calls = 0

    def load() -> list[Broadcast]:
        nonlocal calls
        calls += 1
        return [sample_broadcast]

    clock = Clock()
    cached_at = datetime(2026, 7, 13, 20, tzinfo=UTC)
    cache = BroadcastCache(
        load,
        ttl_seconds=60,
        clock=clock,
        wall_clock=lambda: cached_at,
    )

    first_result = cache.get()
    assert first_result.broadcasts == [sample_broadcast]
    assert first_result.cached_at == cached_at
    clock.now = 59
    assert cache.get().cached_at == cached_at
    assert calls == 1


def test_cache_serves_stale_result_after_error(sample_broadcast: Broadcast) -> None:
    should_fail = False

    def load() -> list[Broadcast]:
        if should_fail:
            raise YouTubeError('failed')
        return [sample_broadcast]

    clock = Clock()
    cached_at = datetime(2026, 7, 13, 20, tzinfo=UTC)
    cache = BroadcastCache(
        load,
        ttl_seconds=60,
        clock=clock,
        wall_clock=lambda: cached_at,
    )
    cache.get()
    should_fail = True
    clock.now = 61

    result = cache.get()

    assert result.broadcasts == [sample_broadcast]
    assert result.is_stale is True
    assert result.cached_at == cached_at


def test_cache_raises_initial_error() -> None:
    def load() -> list[Broadcast]:
        raise YouTubeError('failed')

    cache = BroadcastCache(load, ttl_seconds=60)

    with pytest.raises(YouTubeError):
        cache.get()
