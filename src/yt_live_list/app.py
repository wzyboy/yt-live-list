import os
import logging
from pathlib import Path
from datetime import timedelta

from fastapi import FastAPI
from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

from yt_live_list.cache import BroadcastCache
from yt_live_list.youtube import YouTubeError
from yt_live_list.youtube import YouTubeClient
from yt_live_list.youtube import BroadcastSource
from yt_live_list.youtube import ConfigurationError

LOGGER = logging.getLogger(__name__)
PACKAGE_DIR = Path(__file__).parent


def create_app(
    source: BroadcastSource | None = None,
    cache_ttl_seconds: float | None = None,
) -> FastAPI:
    if source is None:
        token_path = os.environ.get('YTLL_TOKEN_FILE')
        if not token_path:
            raise ConfigurationError('YTLL_TOKEN_FILE is required')
        source = YouTubeClient(Path(token_path))

    if cache_ttl_seconds is None:
        cache_ttl_seconds = _cache_ttl_from_environment()
    if cache_ttl_seconds <= 0:
        raise ConfigurationError('Cache TTL must be greater than zero')

    app = FastAPI(title='YouTube Live List')
    templates = Jinja2Templates(directory=PACKAGE_DIR / 'templates')
    templates.env.filters['format_duration'] = format_duration
    cache = BroadcastCache(source.list_broadcasts, cache_ttl_seconds)
    app.mount('/static', StaticFiles(directory=PACKAGE_DIR / 'static'), name='static')

    @app.get('/', response_class=HTMLResponse)
    async def index(request: Request) -> HTMLResponse:
        try:
            result = cache.get()
        except YouTubeError:
            LOGGER.exception('Unable to load broadcasts from YouTube')
            return templates.TemplateResponse(
                request=request,
                name='error.html',
                status_code=503,
            )

        groups = {
            status: [item for item in result.broadcasts if item.status == status]
            for status in ('active', 'upcoming', 'completed')
        }
        return templates.TemplateResponse(
            request=request,
            name='index.html',
            context={
                'groups': groups,
                'is_stale': result.is_stale,
                'cached_at': result.cached_at,
                'social_preview_url': _social_preview_url(request),
            },
        )

    @app.get('/healthz')
    async def healthz() -> dict[str, str]:
        return {'status': 'ok'}

    return app


def _cache_ttl_from_environment() -> float:
    raw_value = os.environ.get('YTLL_CACHE_TTL_SECONDS', '60')
    try:
        return float(raw_value)
    except ValueError as error:
        raise ConfigurationError('YTLL_CACHE_TTL_SECONDS must be a number') from error


def _social_preview_url(request: Request) -> str:
    public_base_url = os.environ.get('YTLL_PUBLIC_BASE_URL')
    if public_base_url:
        return f'{public_base_url.rstrip('/')}/static/social-preview.png'
    return str(request.url_for('static', path='social-preview.png'))


def format_duration(duration: timedelta) -> str:
    total_minutes = int(duration.total_seconds() // 60)
    if total_minutes < 1:
        return '<1m'
    days, remaining_minutes = divmod(total_minutes, 24 * 60)
    hours, minutes = divmod(remaining_minutes, 60)
    parts = []
    if days:
        parts.append(f'{days}d')
    if hours:
        parts.append(f'{hours}h')
    if minutes or not parts:
        parts.append(f'{minutes}m')
    return ' '.join(parts)
