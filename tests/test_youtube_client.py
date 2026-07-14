import json
from typing import Any
from threading import Lock
from threading import Barrier

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


class FakeServer:
    def __init__(
        self,
        responses: dict[tuple[str, str | None], FakeResponse],
        synchronize_first_pages: bool = False,
    ) -> None:
        self._responses = responses
        self._barrier = Barrier(3, timeout=2) if synchronize_first_pages else None
        self._lock = Lock()
        self.parameters: list[dict[str, Any]] = []
        self.closed_sessions = 0

    def session(self) -> 'FakeSession':
        return FakeSession(self)

    def get(self, params: dict[str, Any]) -> FakeResponse:
        page_token = params.get('pageToken')
        if self._barrier is not None and page_token is None:
            self._barrier.wait()
        with self._lock:
            self.parameters.append(params)
        return self._responses[(params['broadcastStatus'], page_token)]

    def close_session(self) -> None:
        with self._lock:
            self.closed_sessions += 1


class FakeSession:
    def __init__(self, server: FakeServer) -> None:
        self._server = server

    def get(
        self,
        url: str,
        params: dict[str, Any],
        timeout: float,
    ) -> FakeResponse:
        assert url == 'https://www.googleapis.com/youtube/v3/liveBroadcasts'
        assert timeout == 10
        return self._server.get(params)

    def close(self) -> None:
        self._server.close_session()


class FakeCredentials:
    valid = True

    def refresh(self, request: object) -> None:
        raise AssertionError('Valid credentials should not be refreshed')


def client_for(server: FakeServer) -> YouTubeClient:
    client = object.__new__(YouTubeClient)
    client._credentials = FakeCredentials()  # type: ignore[attr-defined]
    client._session_factory = server.session  # type: ignore[attr-defined]
    client._timeout_seconds = 10  # type: ignore[attr-defined]
    return client


def item(
    video_id: str,
    start: str,
    status: str = 'completed',
    privacy_status: str = 'unlisted',
) -> dict[str, object]:
    life_cycle_status = {
        'active': 'live',
        'upcoming': 'ready',
        'completed': 'complete',
    }[status]
    return {
        'id': video_id,
        'snippet': {'title': video_id, 'actualStartTime': start},
        'status': {
            'lifeCycleStatus': life_cycle_status,
            'privacyStatus': privacy_status,
        },
    }


def empty_status_responses() -> dict[tuple[str, str | None], FakeResponse]:
    return {
        ('active', None): FakeResponse({'items': []}),
        ('upcoming', None): FakeResponse({'items': []}),
        ('completed', None): FakeResponse({'items': []}),
    }


def test_client_fetches_statuses_concurrently_and_follows_current_pages() -> None:
    completed = [
        item(f'completed-{day}', f'2026-01-{day:02d}T00:00:00Z')
        for day in range(20, 0, -1)
    ]
    server = FakeServer(
        {
            ('active', None): FakeResponse(
                {
                    'items': [item('active-old', '2026-02-01T00:00:00Z', 'active')],
                    'nextPageToken': 'active-next',
                }
            ),
            ('active', 'active-next'): FakeResponse(
                {
                    'items': [
                        item('active-new', '2026-03-01T00:00:00Z', 'active')
                    ]
                }
            ),
            ('upcoming', None): FakeResponse(
                {
                    'items': [
                        item('upcoming', '2026-04-01T00:00:00Z', 'upcoming')
                    ]
                }
            ),
            ('completed', None): FakeResponse(
                {'items': completed, 'nextPageToken': 'completed-next'}
            ),
        },
        synchronize_first_pages=True,
    )

    result = client_for(server).list_broadcasts()

    assert [broadcast.video_id for broadcast in result[:3]] == [
        'active-new',
        'active-old',
        'upcoming',
    ]
    assert [broadcast.video_id for broadcast in result[3:]] == [
        f'completed-{day}' for day in range(20, 0, -1)
    ]
    assert server.closed_sessions == 3
    first_page_parameters = {
        parameters['broadcastStatus']: parameters
        for parameters in server.parameters
        if 'pageToken' not in parameters
    }
    assert first_page_parameters['active']['maxResults'] == 50
    assert first_page_parameters['upcoming']['maxResults'] == 50
    assert first_page_parameters['completed']['maxResults'] == 20
    assert all(
        parameters['broadcastType'] == 'all' for parameters in server.parameters
    )
    assert not any(
        parameters.get('pageToken') == 'completed-next'
        for parameters in server.parameters
    )


def test_client_continues_completed_pages_until_twenty_usable_results() -> None:
    first_page = [
        item(f'public-{day}', f'2026-01-{day:02d}T00:00:00Z')
        for day in range(20, 5, -1)
    ] + [
        item(
            f'private-{day}',
            f'2026-01-{day:02d}T00:00:00Z',
            privacy_status='private',
        )
        for day in range(5, 0, -1)
    ]
    second_page = [
        item(f'older-{day}', f'2025-12-{day:02d}T00:00:00Z')
        for day in range(31, 26, -1)
    ]
    responses = empty_status_responses()
    responses[('completed', None)] = FakeResponse(
        {'items': first_page, 'nextPageToken': 'completed-next'}
    )
    responses[('completed', 'completed-next')] = FakeResponse(
        {'items': second_page, 'nextPageToken': 'unused-next'}
    )
    server = FakeServer(responses)

    result = client_for(server).list_broadcasts()

    assert len(result) == 20
    assert sum(
        parameters['broadcastStatus'] == 'completed'
        for parameters in server.parameters
    ) == 2
    assert not any(
        parameters.get('pageToken') == 'unused-next'
        for parameters in server.parameters
    )


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

    responses = empty_status_responses()
    responses[('active', None)] = ErrorResponse({})
    server = FakeServer(responses)

    with pytest.raises(
        YouTubeError,
        match='HTTP 403: quotaExceeded',
    ):
        client_for(server).list_broadcasts()

    assert server.closed_sessions == 3
