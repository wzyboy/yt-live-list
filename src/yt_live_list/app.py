import logging
import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from yt_live_list.cache import BroadcastCache
from yt_live_list.youtube import BroadcastSource, ConfigurationError, YouTubeClient, YouTubeError


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
            context={'groups': groups, 'is_stale': result.is_stale},
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
