import json
from typing import Any

import pytest
from requests import Response
from requests import HTTPError

from yt_live_list.youtube import YouTubeError
from yt_live_list.youtube import YouTubeClient


class FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return self._payload


class FakeSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self._responses = responses
        self.parameters: list[dict[str, Any]] = []

    def get(
        self,
        url: str,
        params: dict[str, Any],
        timeout: float,
    ) -> FakeResponse:
        assert url == 'https://www.googleapis.com/youtube/v3/liveBroadcasts'
        assert timeout == 10
        self.parameters.append(params)
        return self._responses.pop(0)


def item(video_id: str, start: str) -> dict[str, object]:
    return {
        'id': video_id,
        'snippet': {'title': video_id, 'actualStartTime': start},
        'status': {
            'lifeCycleStatus': 'complete',
            'privacyStatus': 'unlisted',
        },
    }


def test_client_follows_pages_and_sorts_results() -> None:
    session = FakeSession(
        [
            FakeResponse(
                {
                    'items': [item('older', '2026-01-01T00:00:00Z')],
                    'nextPageToken': 'next-page',
                }
            ),
            FakeResponse({'items': [item('newer', '2026-02-01T00:00:00Z')]}),
        ]
    )
    client = object.__new__(YouTubeClient)
    client._session = session  # type: ignore[attr-defined]
    client._timeout_seconds = 10  # type: ignore[attr-defined]

    result = client.list_broadcasts()

    assert [broadcast.video_id for broadcast in result] == ['newer', 'older']
    assert session.parameters[0]['broadcastType'] == 'all'
    assert 'pageToken' not in session.parameters[0]
    assert session.parameters[1]['pageToken'] == 'next-page'


def test_client_reports_youtube_error_reason() -> None:
    response = Response()
    response.status_code = 403
    response._content = json.dumps(
        {
            'error': {
                'errors': [
                    {
                        'reason': 'quotaExceeded',
                        'message': 'Quota exhausted',
                    }
                ]
            }
        }
    ).encode()
    http_error = HTTPError(response=response)

    class ErrorResponse(FakeResponse):
        def raise_for_status(self) -> None:
            raise http_error

    session = FakeSession([ErrorResponse({})])
    client = object.__new__(YouTubeClient)
    client._session = session  # type: ignore[attr-defined]
    client._timeout_seconds = 10  # type: ignore[attr-defined]

    with pytest.raises(
        YouTubeError,
        match='HTTP 403: quotaExceeded',
    ):
        client.list_broadcasts()
