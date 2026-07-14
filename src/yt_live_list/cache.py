import logging
from time import monotonic
from datetime import UTC
from datetime import datetime
from threading import Lock
from dataclasses import dataclass
from collections.abc import Callable

from yt_live_list.models import Broadcast
from yt_live_list.youtube import YouTubeError

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CachedBroadcasts:
    broadcasts: list[Broadcast]
    is_stale: bool
    cached_at: datetime


class BroadcastCache:
    def __init__(
        self,
        loader: Callable[[], list[Broadcast]],
        ttl_seconds: float,
        clock: Callable[[], float] = monotonic,
        wall_clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._loader = loader
        self._ttl_seconds = ttl_seconds
        self._clock = clock
        self._wall_clock = wall_clock or _utc_now
        self._lock = Lock()
        self._broadcasts: list[Broadcast] | None = None
        self._loaded_at = 0.0
        self._cached_at: datetime | None = None

    def get(self) -> CachedBroadcasts:
        now = self._clock()
        if self._is_fresh(now):
            return self._cached_result(False)

        with self._lock:
            now = self._clock()
            if self._is_fresh(now):
                return self._cached_result(False)

            try:
                broadcasts = self._loader()
            except YouTubeError:
                if self._broadcasts is None:
                    raise
                LOGGER.warning(
                    'Unable to refresh broadcasts; serving stale results',
                    exc_info=True,
                )
                return self._cached_result(True)

            self._broadcasts = list(broadcasts)
            self._loaded_at = now
            self._cached_at = self._wall_clock().astimezone(UTC)
            return self._cached_result(False)

    def _is_fresh(self, now: float) -> bool:
        return (
            self._broadcasts is not None
            and self._cached_at is not None
            and now - self._loaded_at < self._ttl_seconds
        )

    def _cached_result(self, is_stale: bool) -> CachedBroadcasts:
        if self._broadcasts is None or self._cached_at is None:
            raise RuntimeError('Cache has not been populated')
        return CachedBroadcasts(list(self._broadcasts), is_stale, self._cached_at)


def _utc_now() -> datetime:
    return datetime.now(UTC)
