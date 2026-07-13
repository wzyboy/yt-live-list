from dataclasses import dataclass
from datetime import datetime
from typing import Literal


BroadcastStatus = Literal['active', 'upcoming', 'completed']


@dataclass(frozen=True, slots=True)
class Broadcast:
    video_id: str
    title: str
    status: BroadcastStatus
    starts_at: datetime
    thumbnail_url: str | None
    privacy_status: str

    @property
    def watch_url(self) -> str:
        return f'https://www.youtube.com/watch?v={self.video_id}'
