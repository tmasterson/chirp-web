"""Loopback-only HTTP API and static frontend for CHIRPQt."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from chirpQt import directory
from chirpQt.webui.service import (
        DriverSession,
        MAX_IMAGE_SIZE,
        TransferManager,
        WebServiceError,
)

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from pydantic import (
        BaseModel,
        ConfigDict,
        Field,
        StrictBool,
        StrictFloat,
        StrictInt,
        StrictStr,
)

LOG = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).with_name('static')


class StrictModel(BaseModel):
    """Reject unknown request fields rather than silently ignoring them."""

    model_config = ConfigDict(extra='forbid')


class OpenImageRequest(StrictModel):
    """Encoded image supplied by the browser."""

    filename: str = Field(min_length=1, max_length=255)
    data_base64: str = Field(max_length=(MAX_IMAGE_SIZE * 4 // 3) + 8)
    confirm_replace: bool = False


class DownloadRequest(StrictModel):
    """Clone download selection."""

    radio_id: str = Field(min_length=1, max_length=200)
    port: str = Field(min_length=1, max_length=512)
    confirm_replace: bool = False


class UploadRequest(StrictModel):
    """Explicitly confirmed clone upload selection."""

    port: str = Field(min_length=1, max_length=512)
    confirm: bool


class MemoryUpdate(StrictModel):
    """Supported editable fields for one memory."""

    name: str | None = Field(default=None, max_length=999)
    freq: int | float | None = Field(default=None, gt=0)
    mode: str | None = Field(default=None, max_length=32)
    duplex: str | None = Field(default=None, max_length=16)
    offset: int | float | None = Field(default=None, ge=0)
    tmode: str | None = Field(default=None, max_length=32)
    rtone: float | None = Field(default=None, ge=0)
    ctone: float | None = Field(default=None, ge=0)
    dtcs: int | None = Field(default=None, ge=0)
    rx_dtcs: int | None = Field(default=None, ge=0)
    dtcs_polarity: str | None = Field(default=None, max_length=2)
    cross_mode: str | None = Field(default=None, max_length=32)
    tuning_step: float | None = Field(default=None, ge=0)
    skip: str | None = Field(default=None, max_length=8)
    comment: str | None = Field(default=None, max_length=4096)


class SettingChange(StrictModel):
    """One setting path and its new typed value."""

    path: list[StrictStr | StrictInt] = Field(min_length=2, max_length=16)
    value: StrictBool | StrictInt | StrictFloat | StrictStr


class SettingsUpdate(StrictModel):
    """Requested radio-level setting changes."""

    changes: list[SettingChange] = Field(min_length=1, max_length=256)
    confirm_warnings: bool = False


def _local_host(host: str) -> bool:
    hostname = host.rsplit(':', 1)[0].strip('[]').lower()
    return hostname in {'127.0.0.1', 'localhost'}


def create_app() -> FastAPI:
    """Create an isolated application and single-user radio session."""
    directory.import_drivers()
    session = DriverSession()
    transfers = TransferManager(session)

    @asynccontextmanager
    async def lifespan(app):
        try:
            yield
        finally:
            transfers.close()

    app = FastAPI(
            title='CHIRPQt Local Web',
            docs_url=None,
            redoc_url=None,
            openapi_url=None,
            lifespan=lifespan,
    )
    app.state.session = session
    app.state.transfers = transfers

    @app.middleware('http')
    async def restrict_to_local_origin(request, call_next):
        host = request.headers.get('host', '')
        origin = request.headers.get('origin')
        if not _local_host(host):
            return JSONResponse(
                    {'detail': 'This service accepts loopback requests only.'},
                    status_code=403)
        if origin:
            parsed = urlsplit(origin)
            if (parsed.scheme != 'http' or
                    parsed.netloc.lower() != host.lower() or
                    not _local_host(parsed.netloc)):
                return JSONResponse(
                        {'detail': 'Cross-origin requests are not allowed.'},
                        status_code=403)
        if request.headers.get('sec-fetch-site') == 'cross-site':
            return JSONResponse(
                    {'detail': 'Cross-site requests are not allowed.'},
                    status_code=403)
        response = await call_next(request)
        response.headers['Content-Security-Policy'] = (
                "default-src 'self'; script-src 'self'; style-src 'self'; "
                "img-src 'self' data:; connect-src 'self'; object-src "
                "'none'; base-uri 'none'; frame-ancestors 'none'")
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['X-Frame-Options'] = 'DENY'
        return response

    @app.exception_handler(WebServiceError)
    async def handle_service_error(request, exc: WebServiceError):
        return JSONResponse(
                {'detail': str(exc)}, status_code=exc.status_code)

    @app.get('/')
    def index():
        return FileResponse(STATIC_DIR / 'index.html')

    app.mount('/static', StaticFiles(directory=STATIC_DIR), name='static')

    @app.get('/api/radios')
    def list_radios():
        return transfers.radios()

    @app.get('/api/ports')
    def list_ports():
        return transfers.ports()

    @app.get('/api/session')
    def get_session():
        return session.describe()

    @app.post('/api/session/open')
    def open_image(payload: OpenImageRequest):
        try:
            return session.open_image(
                    payload.filename,
                    payload.data_base64,
                    confirm_replace=payload.confirm_replace)
        except WebServiceError:
            raise
        except Exception as exc:
            LOG.exception('Unable to open uploaded radio image')
            raise WebServiceError(
                    'The selected file could not be opened by a supported '
                    'radio driver.', 422) from exc

    @app.get('/api/memories')
    def list_memories(start: int | None = Query(default=None),
                      limit: int = Query(default=50, ge=1, le=200)):
        details = session.describe()
        low, high = details['memory_bounds']
        return session.memories(low if start is None else start, limit)

    @app.patch('/api/memories/{number}')
    def update_memory(number: int, payload: MemoryUpdate):
        values = payload.model_dump(exclude_unset=True)
        if any(value is None for value in values.values()):
            raise WebServiceError(
                    'Memory field values cannot be null.', 422)
        return session.update_memory(number, values)

    @app.get('/api/settings')
    def get_settings():
        return session.radio_settings()

    @app.patch('/api/settings')
    def update_settings(payload: SettingsUpdate):
        return session.update_settings(
                [change.model_dump() for change in payload.changes],
                confirm_warnings=payload.confirm_warnings)

    @app.post('/api/session/save')
    def save_image():
        try:
            return session.save_image()
        except WebServiceError:
            raise
        except Exception as exc:
            LOG.exception('Unable to save radio image')
            raise WebServiceError(
                    'The radio driver could not save this image.',
                    500) from exc

    @app.post('/api/transfers/download')
    def download_radio(payload: DownloadRequest):
        return transfers.start(
                'download',
                payload.radio_id,
                payload.port,
                confirm_replace=payload.confirm_replace)

    @app.post('/api/transfers/upload')
    def upload_radio(payload: UploadRequest):
        return transfers.start(
                'upload', '', payload.port, confirm=payload.confirm)

    @app.get('/api/transfers/{job_id}')
    def transfer_status(job_id: str):
        return transfers.get(job_id)

    return app


app = create_app()
