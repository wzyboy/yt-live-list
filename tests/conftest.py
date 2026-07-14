from datetime import UTC
from datetime import datetime

import pytest

from yt_live_list.models import Broadcast


@pytest.fixture
def sample_broadcast() -> Broadcast:
    return Broadcast(
        video_id='abc123',
        title='Game night',
        status='active',
        starts_at=datetime(2026, 7, 13, 18, tzinfo=UTC),
        thumbnail_url='https://example.com/image.jpg',
        privacy_status='unlisted',
    )
