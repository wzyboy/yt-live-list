import logging
from time import monotonic
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


class BroadcastCache:
    def __init__(
        self,
        loader: Callable[[], list[Broadcast]],
        ttl_seconds: float,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self._loader = loader
        self._ttl_seconds = ttl_seconds
        self._clock = clock
        self._lock = Lock()
        self._broadcasts: list[Broadcast] | None = None
        self._loaded_at = 0.0

    def get(self) -> CachedBroadcasts:
        now = self._clock()
        if self._is_fresh(now):
            return CachedBroadcasts(list(self._broadcasts or []), False)

        with self._lock:
            now = self._clock()
            if self._is_fresh(now):
                return CachedBroadcasts(list(self._broadcasts or []), False)

            try:
                broadcasts = self._loader()
            except YouTubeError:
                if self._broadcasts is None:
                    raise
                LOGGER.warning(
                    'Unable to refresh broadcasts; serving stale results',
                    exc_info=True,
                )
                return CachedBroadcasts(list(self._broadcasts), True)

            self._broadcasts = list(broadcasts)
            self._loaded_at = now
            return CachedBroadcasts(list(self._broadcasts), False)

    def _is_fresh(self, now: float) -> bool:
        return (
            self._broadcasts is not None
            and now - self._loaded_at < self._ttl_seconds
        )
