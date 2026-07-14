from typing import Literal
from datetime import datetime
from datetime import timedelta
from dataclasses import dataclass

BroadcastStatus = Literal['active', 'upcoming', 'completed']


@dataclass(frozen=True, slots=True)
class Broadcast:
    video_id: str
    title: str
    status: BroadcastStatus
    starts_at: datetime
    thumbnail_url: str | None
    privacy_status: str
    ends_at: datetime | None = None

    @property
    def watch_url(self) -> str:
        return f'https://www.youtube.com/watch?v={self.video_id}'

    def duration_at(self, reference_time: datetime) -> timedelta | None:
        if self.status == 'upcoming':
            return None
        end_time = self.ends_at if self.status == 'completed' else reference_time
        if end_time is None or end_time < self.starts_at:
            return None
        return end_time - self.starts_at
