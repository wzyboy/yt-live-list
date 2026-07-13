from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import AuthorizedSession
from google.oauth2.credentials import Credentials
from requests import RequestException, Response

from yt_live_list.models import Broadcast, BroadcastStatus


YOUTUBE_READONLY_SCOPE = 'https://www.googleapis.com/auth/youtube.readonly'
LIVE_BROADCASTS_URL = 'https://www.googleapis.com/youtube/v3/liveBroadcasts'


class ConfigurationError(RuntimeError):
    """The local application configuration is invalid."""


class YouTubeError(RuntimeError):
    """YouTube could not provide a usable broadcast list."""


class BroadcastSource(Protocol):
    def list_broadcasts(self) -> list[Broadcast]: ...


class YouTubeClient:
    def __init__(self, token_file: Path, timeout_seconds: float = 10) -> None:
        if not token_file.is_file():
            raise ConfigurationError(f'YouTube token file does not exist: {token_file}')

        try:
            credentials = Credentials.from_authorized_user_file(
                str(token_file),
                scopes=[YOUTUBE_READONLY_SCOPE],
            )
        except (OSError, ValueError, GoogleAuthError) as error:
            raise ConfigurationError(
                f'Could not load YouTube token file: {token_file}'
            ) from error

        self._session = AuthorizedSession(credentials)
        self._timeout_seconds = timeout_seconds

    def list_broadcasts(self) -> list[Broadcast]:
        items: list[Mapping[str, Any]] = []
        page_token: str | None = None
        seen_page_tokens: set[str] = set()

        while True:
            parameters = {
                'part': 'id,snippet,status',
                'broadcastStatus': 'all',
                'broadcastType': 'all',
                'maxResults': 50,
            }
            if page_token is not None:
                parameters['pageToken'] = page_token

            try:
                response = self._session.get(
                    LIVE_BROADCASTS_URL,
                    params=parameters,
                    timeout=self._timeout_seconds,
                )
                response.raise_for_status()
                payload = response.json()
            except RequestException as error:
                if error.response is not None:
                    raise _http_error(error.response) from error
                raise YouTubeError('YouTube API request failed') from error
            except (GoogleAuthError, ValueError) as error:
                raise YouTubeError('YouTube API request failed') from error

            if not isinstance(payload, dict) or not isinstance(payload.get('items'), list):
                raise YouTubeError('YouTube API returned an invalid response')

            items.extend(item for item in payload['items'] if isinstance(item, dict))
            next_page_token = payload.get('nextPageToken')
            if next_page_token is None:
                break
            if not isinstance(next_page_token, str) or next_page_token in seen_page_tokens:
                raise YouTubeError('YouTube API returned an invalid page token')

            seen_page_tokens.add(next_page_token)
            page_token = next_page_token

        broadcasts = [broadcast for item in items if (broadcast := parse_broadcast(item))]
        return sort_and_limit_broadcasts(broadcasts)


def parse_broadcast(item: Mapping[str, Any]) -> Broadcast | None:
    video_id = item.get('id')
    snippet = item.get('snippet')
    status_data = item.get('status')
    if (
        not isinstance(video_id, str)
        or not video_id
        or not isinstance(snippet, dict)
        or not isinstance(status_data, dict)
    ):
        return None

    privacy_status = status_data.get('privacyStatus')
    life_cycle_status = status_data.get('lifeCycleStatus')
    if privacy_status not in {'public', 'unlisted'} or life_cycle_status == 'revoked':
        return None

    starts_at = _first_datetime(
        snippet,
        'actualStartTime',
        'scheduledStartTime',
        'publishedAt',
    )
    if starts_at is None:
        return None

    broadcast_status = _classify_status(snippet, life_cycle_status)
    if broadcast_status is None:
        return None

    title = snippet.get('title')
    if not isinstance(title, str) or not title.strip():
        title = 'Untitled stream'

    return Broadcast(
        video_id=video_id,
        title=title,
        status=broadcast_status,
        starts_at=starts_at,
        thumbnail_url=_thumbnail_url(snippet.get('thumbnails')),
        privacy_status=privacy_status,
    )


def sort_and_limit_broadcasts(
    broadcasts: list[Broadcast], history_limit: int = 20
) -> list[Broadcast]:
    active = sorted(
        (item for item in broadcasts if item.status == 'active'),
        key=lambda item: item.starts_at,
        reverse=True,
    )
    upcoming = sorted(
        (item for item in broadcasts if item.status == 'upcoming'),
        key=lambda item: item.starts_at,
    )
    completed = sorted(
        (item for item in broadcasts if item.status == 'completed'),
        key=lambda item: item.starts_at,
        reverse=True,
    )[:history_limit]
    return [*active, *upcoming, *completed]


def _classify_status(
    snippet: Mapping[str, Any], life_cycle_status: object
) -> BroadcastStatus | None:
    if _parse_datetime(snippet.get('actualEndTime')) is not None:
        return 'completed'
    if life_cycle_status == 'complete':
        return 'completed'
    if life_cycle_status in {'live', 'liveStarting'}:
        return 'active'
    if life_cycle_status in {'created', 'ready', 'testStarting', 'testing'}:
        return 'upcoming'
    if _parse_datetime(snippet.get('actualStartTime')) is not None:
        return 'active'
    if _parse_datetime(snippet.get('scheduledStartTime')) is not None:
        return 'upcoming'
    return None


def _first_datetime(data: Mapping[str, Any], *keys: str) -> datetime | None:
    for key in keys:
        if parsed := _parse_datetime(data.get(key)):
            return parsed
    return None


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _thumbnail_url(thumbnails: object) -> str | None:
    if not isinstance(thumbnails, dict):
        return None
    for size in ('maxres', 'standard', 'high', 'medium', 'default'):
        thumbnail = thumbnails.get(size)
        if isinstance(thumbnail, dict) and isinstance(thumbnail.get('url'), str):
            return thumbnail['url']
    return None


def _http_error(response: Response) -> YouTubeError:
    reason = 'unknownError'
    try:
        payload = response.json()
    except ValueError:
        payload = None

    if isinstance(payload, dict):
        error_data = payload.get('error')
        if isinstance(error_data, dict):
            errors = error_data.get('errors')
            if isinstance(errors, list) and errors and isinstance(errors[0], dict):
                candidate = errors[0].get('reason')
                if isinstance(candidate, str):
                    reason = candidate

    return YouTubeError(
        f'YouTube API request failed with HTTP {response.status_code}: {reason}'
    )
