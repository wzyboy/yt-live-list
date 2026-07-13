from datetime import UTC, datetime, timedelta

from yt_live_list.models import Broadcast
from yt_live_list.youtube import parse_broadcast, sort_and_limit_broadcasts


def api_item(
    video_id: str = 'video-1',
    life_cycle_status: str = 'live',
    privacy_status: str = 'unlisted',
    start: str = '2026-07-13T18:00:00Z',
) -> dict[str, object]:
    return {
        'id': video_id,
        'snippet': {
            'title': 'Game night',
            'actualStartTime': start,
            'thumbnails': {'high': {'url': 'https://example.com/image.jpg'}},
        },
        'status': {
            'lifeCycleStatus': life_cycle_status,
            'privacyStatus': privacy_status,
        },
    }


def test_parse_unlisted_live_broadcast() -> None:
    broadcast = parse_broadcast(api_item())

    assert broadcast is not None
    assert broadcast.video_id == 'video-1'
    assert broadcast.status == 'active'
    assert broadcast.watch_url == 'https://www.youtube.com/watch?v=video-1'
    assert broadcast.starts_at == datetime(2026, 7, 13, 18, tzinfo=UTC)


def test_parse_excludes_private_and_malformed_broadcasts() -> None:
    assert parse_broadcast(api_item(privacy_status='private')) is None
    assert parse_broadcast({'id': 'missing-fields'}) is None


def test_sort_groups_and_limits_completed_history() -> None:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    completed = [
        Broadcast(
            str(index),
            str(index),
            'completed',
            base + timedelta(days=index),
            None,
            'unlisted',
        )
        for index in range(25)
    ]
    active = Broadcast('live', 'Live', 'active', base, None, 'unlisted')
    upcoming_late = Broadcast(
        'later', 'Later', 'upcoming', base + timedelta(days=2), None, 'unlisted'
    )
    upcoming_soon = Broadcast(
        'soon', 'Soon', 'upcoming', base + timedelta(days=1), None, 'unlisted'
    )

    result = sort_and_limit_broadcasts(
        [*completed, upcoming_late, active, upcoming_soon]
    )

    assert result[0] == active
    assert result[1:3] == [upcoming_soon, upcoming_late]
    assert len([item for item in result if item.status == 'completed']) == 20
    assert result[3].video_id == '24'
