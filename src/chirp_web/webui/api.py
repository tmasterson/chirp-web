"""Loopback-only HTTP API and static frontend for CHIRP Web."""

# Copyright 2026 Tom Masterson <kd7cyu@gmail.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import logging
import json
import math
import platform
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from importlib import metadata
from pathlib import Path
from typing import Callable, Protocol, TypedDict, cast
from urllib.parse import urlsplit

from chirp_web import chirp_common, directory
from chirp_web.sources import (
        dmrmarc,
        mapy73pl,
        przemienniki_eu,
        przemienniki_net,
        radioreference,
        repeaterbook,
        satellites,
)
from chirp_web.webui.service import (
        DriverSession,
        MAX_IMAGE_SIZE,
        TransferManager,
        WebServiceError,
)

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, JSONResponse, Response
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
    confirm_prompts: bool = False


class UploadRequest(StrictModel):
    """Explicitly confirmed clone upload selection."""

    port: str = Field(min_length=1, max_length=512)
    confirm: bool
    confirm_prompts: bool = False


class MemoryUpdate(StrictModel):
    """Supported editable fields for one memory."""

    name: str | None = Field(default=None, max_length=999)
    freq: int | float | None = Field(default=None, gt=0)
    txfreq: int | float | None = Field(default=None, gt=0)
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
    power: float | None = None
    extra_changes: list['ExtraChange'] | None = Field(
            default=None, max_length=128)


class ExtraChange(StrictModel):
    """One driver-specific memory field change."""

    path: list[StrictStr | StrictInt] = Field(min_length=2, max_length=16)
    value: StrictBool | StrictInt | StrictFloat | StrictStr


class MemoryDelete(StrictModel):
    """Selected memories to erase from the open image."""

    numbers: list[StrictInt | StrictStr] = Field(
            min_length=1, max_length=200)
    shift: str = Field(default='', pattern='^(|block|all)$')


class MemoryMove(StrictModel):
    """Request to move numbered channels up or down."""

    numbers: list[StrictInt] = Field(min_length=1, max_length=200)
    direction: str = Field(pattern='^(up|down)$')


class MemoryInsert(StrictModel):
    """Request to open an empty row at a numbered channel."""

    number: StrictInt = Field(ge=0)


class MemoryCopy(StrictModel):
    """Request to copy or cut selected channels."""

    numbers: list[StrictInt | StrictStr] = Field(
            min_length=1, max_length=200)
    cut: bool = False


class MemoryPaste(StrictModel):
    """Request to paste clipboard contents at a numbered channel."""

    clipboard_id: StrictStr = Field(min_length=1, max_length=64)
    start: StrictInt = Field(ge=0)
    overwrite: bool = False


class MemoryBulkUpdate(StrictModel):
    """Apply one validated set of field changes to selected channels."""

    numbers: list[StrictInt | StrictStr] = Field(
            min_length=2, max_length=200)
    changes: MemoryUpdate


class MemoryArrange(StrictModel):
    """Sort or cluster a contiguous set of numbered channels."""

    numbers: list[StrictInt] = Field(min_length=2, max_length=200)
    operation: str = Field(pattern='^(sort|cluster)$')
    field: str = Field(default='name', max_length=32)
    direction: str = Field(default='asc', pattern='^(asc|desc)$')


class NewConfiguration(StrictModel):
    """Request to create a new image from a built-in template."""

    template_id: StrictStr = Field(min_length=1, max_length=64)
    confirm_replace: bool = False


class ImportImageRequest(StrictModel):
    """An image whose memories should be merged into the open image."""

    filename: str = Field(min_length=1, max_length=255)
    data_base64: str = Field(max_length=(MAX_IMAGE_SIZE * 4 // 3) + 8)
    placement: str = Field(default='empty',
                           pattern='^(empty|matching|append|range)$')
    destination_start: StrictInt | None = Field(default=None, ge=0)


class BackupStorageSettings(StrictModel):
    """Opt-in local directory and retention policy for clone backups."""

    directory: StrictStr | None = Field(default=None, max_length=4096)
    retention: StrictInt = Field(default=10, ge=1, le=100)


class TabOrder(StrictModel):
    """Ordered identifiers for every open image tab."""

    tab_ids: list[StrictStr] = Field(min_length=1, max_length=64)


class BankUpdate(StrictModel):
    """Rename a bank or set a channel's position within it."""

    model: StrictStr = Field(min_length=1, max_length=128)
    bank_index: StrictStr | StrictInt
    name: StrictStr | None = Field(default=None, max_length=64)
    memory_number: StrictInt | None = None
    index: StrictInt | None = Field(default=None, ge=0)


class BandplanUpdate(StrictModel):
    """Select the bandplan used by frequency defaults."""

    name: StrictStr = Field(min_length=1, max_length=32)


class FrequencyDefaultsRequest(StrictModel):
    """Frequency in MHz for the bandplan helper."""

    frequency: StrictFloat | StrictInt = Field(gt=0)


class BankMembershipRequest(StrictModel):
    """Toggle one memory's membership in a bank model."""

    model: str | None = Field(default=None, max_length=128)
    bank_index: StrictStr | StrictInt = Field(default=0)
    enabled: bool = True


class SettingChange(StrictModel):
    """One setting path and its new typed value."""

    path: list[StrictStr | StrictInt] = Field(min_length=2, max_length=16)
    value: StrictBool | StrictInt | StrictFloat | StrictStr


class SettingsUpdate(StrictModel):
    """Requested radio-level setting changes."""

    changes: list[SettingChange] = Field(min_length=1, max_length=256)
    confirm_warnings: bool = False


class MemoryFilter(StrictModel):
    """One structured channel filter."""

    field: str = Field(
            pattern='^(name|freq|mode|duplex|tmode|comment|skip)$')
    operator: str = Field(pattern='^(equals|contains|matches|range|in)$')
    value: StrictStr | StrictInt | StrictFloat | list[
            StrictStr | StrictInt | StrictFloat]


class MemoryQuery(StrictModel):
    """Structured channel list query."""

    filters: list[MemoryFilter] = Field(default_factory=list, max_length=12)
    match: str = Field(default='all', pattern='^(all|any)$')
    start: StrictInt = Field(default=0, ge=0)
    limit: StrictInt = Field(default=50, ge=1, le=200)
    sort: str = Field(default='number',
                      pattern='^(number|name|freq|mode|duplex)$')
    direction: str = Field(default='asc', pattern='^(asc|desc)$')
    hide_empty: StrictBool = False


class MemoryScope(StrictModel):
    """An explicit print or CSV-export selection."""

    scope: str = Field(pattern='^(all|selected|filtered)$')
    numbers: list[StrictInt | StrictStr] = Field(default_factory=list,
                                                   max_length=1000)
    filters: list[MemoryFilter] = Field(default_factory=list, max_length=12)
    match: str = Field(default='all', pattern='^(all|any)$')
    search: str = Field(default='', max_length=200)
    sort: str = Field(default='number',
                      pattern='^(number|name|freq|mode|duplex)$')
    direction: str = Field(default='asc', pattern='^(asc|desc)$')
    hide_empty: StrictBool = False


class TabMemoryCompare(StrictModel):
    """Selected memories compared with another open image tab."""

    tab_id: StrictStr = Field(min_length=1, max_length=64)
    numbers: list[StrictInt | StrictStr] = Field(min_length=1, max_length=200)


class SupportReportRequest(StrictModel):
    """User-selected safe attachments for a support report."""

    include: list[StrictStr] = Field(min_length=1, max_length=8)


class RecoveryImport(StrictModel):
    """Explicit browser-provided image snapshots for recovery."""

    tabs: list[dict[StrictStr, StrictStr]] = Field(min_length=1,
                                                     max_length=16)


class SourceQuery(StrictModel):
    """Source-specific search parameters submitted by the browser."""

    params: dict[StrictStr, object] = Field(default_factory=dict)


class SourceImport(StrictModel):
    """Selected result indexes from one source query."""

    query_id: StrictStr = Field(min_length=1, max_length=64)
    selected: list[StrictInt] = Field(min_length=1, max_length=1000)


class SourceQueryStatus:
    """Capture progress and failure state from a network source."""

    def __init__(self, cancelled=None, update=None):
        self.updates = []
        self.failures = []
        self.ended = False
        self.cancelled = cancelled or threading.Event()
        self.update = update

    def send_status(self, message, percent):
        if self.cancelled.is_set():
            raise WebServiceError('Source query was cancelled.', 409)
        status = {
            'message': str(message),
            'percent': max(0, min(100, int(percent))),
        }
        self.updates.append(status)
        if self.update:
            self.update(status)

    def send_end(self):
        self.ended = True

    def send_fail(self, reason):
        self.failures.append(str(reason))


class SourceQueryManager:
    """Run network source queries without blocking HTTP request workers."""

    def __init__(self, session):
        self.session = session
        self.executor = ThreadPoolExecutor(
                max_workers=2, thread_name_prefix='chirp-web-source')
        self.lock = threading.Lock()
        self.jobs = {}
        self.results = {}
        self.history = []

    @staticmethod
    def _safe_params(params):
        return {
            key: value for key, value in params.items()
            if key.casefold() not in {'password', 'username', 'token',
                                      'api_key', 'apikey'}
        }

    def start(self, source_id, source, params, tab_id):
        job_id = str(uuid.uuid4())
        job = {
            'id': job_id, 'state': 'running', 'progress': 0,
            'message': 'Starting source query', 'result': None,
            'error': None, 'cancelled': threading.Event(),
            'source_id': source_id, 'source': source['name'],
            'params': self._safe_params(params),
            'started_at': time.monotonic(),
        }
        with self.lock:
            self.jobs[job_id] = job
        self.executor.submit(
                self._run, job_id, source_id, source, params, tab_id)
        return self._public(job)

    @staticmethod
    def _public(job):
        return {key: value for key, value in job.items()
                if key != 'cancelled'}

    def _update(self, job_id, status):
        with self.lock:
            job = self.jobs[job_id]
            job['message'] = status['message']
            job['progress'] = status['percent']

    def _run(self, job_id, source_id, source, params, tab_id):
        with self.lock:
            job = self.jobs[job_id]
        status = SourceQueryStatus(
                job['cancelled'],
                lambda update: self._update(job_id, update))
        try:
            radio = source['radio']()
            if source_id == 'radioreference':
                username = params.pop('username')
                password = params.pop('password')
                cast(RadioReferenceSourceRadio, radio).set_auth(
                        username, password)
            radio.do_fetch(status, params)
            if job['cancelled'].is_set():
                raise WebServiceError('Source query was cancelled.', 409)
            if status.failures:
                raise WebServiceError(status.failures[-1], 502)
            if not status.ended:
                raise WebServiceError(
                        'The selected source did not complete its query.',
                        502)
            low, high = radio.get_features().memory_bounds
            memories = []
            for number in range(low, high + 1):
                memory = radio.get_memory(number)
                if not memory.empty:
                    memories.append(memory)
            query_id = str(uuid.uuid4())
            with self.lock:
                self.results[query_id] = memories
            result = {
                'query_id': query_id, 'source': source['name'],
                'count': len(memories),
                'memories': [
                    {**self.session._memory_dict(memory), 'number': index}
                    for index, memory in enumerate(memories)
                ],
            }
            with self.lock:
                job.update(
                        state='complete', progress=100,
                        message='Source query complete', result=result)
        except Exception as exc:
            if isinstance(exc, WebServiceError) and exc.status_code == 409:
                state, message = 'cancelled', str(exc)
            else:
                LOG.exception('Network source %s query failed', source_id)
                state, message = 'failed', 'The selected source query failed.'
            with self.lock:
                job.update(state=state, error=message, message=message)
        finally:
            with self.lock:
                job = self.jobs[job_id]
                record = {
                    key: job[key] for key in (
                        'id', 'source_id', 'source', 'params', 'state',
                        'error')
                }
                record['count'] = (job['result'] or {}).get('count', 0)
                record['duration_ms'] = int(
                        (time.monotonic() - job['started_at']) * 1000)
                self.history.insert(0, record)
                del self.history[20:]

    def get(self, job_id):
        with self.lock:
            job = self.jobs.get(job_id)
            if job is None:
                raise WebServiceError('Source query job was not found.', 404)
            return self._public(job)

    def cancel(self, job_id):
        with self.lock:
            job = self.jobs.get(job_id)
            if job is None:
                raise WebServiceError('Source query job was not found.', 404)
            if job['state'] == 'running':
                job['cancelled'].set()
                job.update(message='Cancelling source query')
            return self._public(job)

    def import_results(self, query_id, selected):
        with self.lock:
            memories = self.results.pop(query_id, None)
        if memories is None:
            raise WebServiceError('Source results have expired.', 404)
        token = self.session.remember_source_results(memories)
        return self.session.import_source_results(token, selected)

    def history_summary(self):
        with self.lock:
            return {'jobs': [dict(item) for item in self.history]}

    def retry(self, history_id, catalog, tab_id):
        with self.lock:
            record = next(
                    (item for item in self.history
                     if item['id'] == history_id), None)
        if record is None:
            raise WebServiceError('Source query history was not found.', 404)
        source = catalog.get(record['source_id'])
        if source is None:
            raise WebServiceError('The saved source is no longer available.',
                                  404)
        if record['source_id'] == 'radioreference':
            raise WebServiceError(
                    'Re-enter RadioReference credentials before retrying.',
                    409)
        return self.start(record['source_id'], source,
                          dict(record['params']), tab_id)

    def close(self):
        self.executor.shutdown(wait=False, cancel_futures=True)


class SourceRadio(Protocol):
    def do_fetch(self, status: SourceQueryStatus,
                 params: dict[str, object]) -> None: ...

    def get_features(self) -> chirp_common.RadioFeatures: ...

    def get_memory(self, number: int) -> chirp_common.Memory: ...


class RadioReferenceSourceRadio(SourceRadio, Protocol):
    def set_auth(self, username: str, password: str) -> None: ...


class SourceCatalogEntry(TypedDict):
    name: str
    radio: Callable[[], SourceRadio]
    example: dict[str, object]
    help: str
    fields: list[dict[str, object]]


SOURCE_CATALOG: dict[str, SourceCatalogEntry] = {
    'mapy73': {
        'name': 'mapy73.pl',
        'radio': mapy73pl.Mapy73Pl,
        'example': {'api_option': 'pl-fmpoland'},
        'help': 'Search a public repeater snapshot by network or country.',
        'fields': [
            {'name': 'api_option', 'label': 'Network / region',
             'type': 'select', 'default': 'pl-fmpoland',
             'options': [
                 'pl-fmpoland', 'pl-fmlink', 'pl-dmr', 'pl-c4fm',
                 'pl-dstar', 'pl-fm', 'cz-fm', 'sk-fm', 'fi-fm',
                 'se-fm', 'no-fm', 'bg-fm', 'dk-fm', 'de-fm', 'si-fm',
                 'is-fm',
             ]},
        ],
    },
    'amsat': {
        'name': 'AMSAT active satellite frequencies',
        'radio': satellites.AmateurSatellites,
        'example': {},
        'help': 'Current satellite downlink and uplink frequencies.',
        'fields': [],
    },
    'satnogs': {
        'name': 'SatNOGS',
        'radio': satellites.SatNOGS,
        'example': {'modes': ''},
        'help': 'Active satellite transmitters. Optionally filter by '
                'comma-separated modes.',
        'fields': [
            {'name': 'modes', 'label': 'Modes (optional)', 'type': 'list',
             'placeholder': 'FM, USB, CW'},
        ],
    },
    'dmrmarc': {
        'name': 'DMR-MARC',
        'radio': dmrmarc.DMRMARCRadio,
        'example': {'city': '', 'state': '', 'country': ''},
        'help': 'Search by city, state, and country.',
        'fields': [
            {'name': 'city', 'label': 'City', 'type': 'text',
             'required': True},
            {'name': 'state', 'label': 'State / region', 'type': 'text',
             'required': True},
            {'name': 'country', 'label': 'Country', 'type': 'text',
             'required': True},
        ],
    },
    'przemienniki-eu': {
        'name': 'przemienniki.eu',
        'radio': przemienniki_eu.PrzemiennikiEu,
        'example': {},
        'help': 'Pass the search parameters accepted by przemienniki.eu.',
        'fields': [],
    },
    'przemienniki-net': {
        'name': 'przemienniki.net',
        'radio': przemienniki_net.PrzemiennikiNet,
        'example': {'range': '0'},
        'help': 'Pass the search parameters accepted by przemienniki.net.',
        'fields': [
            {'name': 'range', 'label': 'Range', 'type': 'text',
             'default': '0'},
        ],
    },
    'radioreference': {
        'name': 'RadioReference',
        'radio': radioreference.RadioReferenceRadio,
        'example': {
            'username': '',
            'password': '',
            'country': 'US',
            'zipcounty': '',
        },
        'help': 'Requires a RadioReference account and a US ZIP code or '
                'Canadian county ID.',
        'fields': [
            {'name': 'username', 'label': 'Username', 'type': 'text',
             'required': True},
            {'name': 'password', 'label': 'Password', 'type': 'password',
             'required': True},
            {'name': 'country', 'label': 'Country', 'type': 'select',
             'options': ['US', 'CA'], 'default': 'US'},
            {'name': 'zipcounty', 'label': 'ZIP code / county ID',
             'type': 'text', 'required': True},
        ],
    },
    'repeaterbook': {
        'name': 'RepeaterBook',
        'radio': repeaterbook.RepeaterBook,
        'example': {
            'country': 'United States',
            'state': 'California',
            'service': 'amateur',
            'service_display': 'Amateur',
            'filter': '',
            'lat': 0,
            'lon': 0,
            'dist': 0,
            'bands': [],
            'modes': [],
            'fmconv': False,
            'openonly': False,
            'cached': False,
        },
        'help': 'Set country, state, and service; optional filters include '
                'location, distance, bands, and modes.',
        'fields': [
            {'name': 'country', 'label': 'Country', 'type': 'text',
             'required': True, 'default': 'United States'},
            {'name': 'state', 'label': 'State / region', 'type': 'text'},
            {'name': 'service', 'label': 'Service', 'type': 'text',
             'required': True, 'default': 'amateur'},
            {'name': 'filter', 'label': 'Keyword filter', 'type': 'text'},
            {'name': 'lat', 'label': 'Latitude', 'type': 'number'},
            {'name': 'lon', 'label': 'Longitude', 'type': 'number'},
            {'name': 'dist', 'label': 'Distance (km)', 'type': 'number'},
            {'name': 'bands', 'label': 'Bands (MHz ranges, comma-separated)',
             'type': 'bands'},
            {'name': 'modes', 'label': 'Modes (comma-separated)',
             'type': 'list'},
            {'name': 'fmconv', 'label': 'Convert compatible entries to FM',
             'type': 'boolean'},
            {'name': 'openonly', 'label': 'Open repeaters only',
             'type': 'boolean'},
            {'name': 'cached', 'label': 'Include cached nearby results',
             'type': 'boolean'},
        ],
    },
}


def _validate_source_params(params):
    if len(params) > 100:
        raise WebServiceError('Too many source search parameters.', 422)

    def validate_value(value, depth=0):
        if depth > 3:
            return False
        if value is None or type(value) in (str, int, float, bool):
            if isinstance(value, float) and not math.isfinite(value):
                return False
            return not isinstance(value, str) or len(value) <= 2048
        if isinstance(value, list):
            return len(value) <= 1000 and all(
                    validate_value(item, depth + 1) for item in value)
        return False

    for key, value in params.items():
        if not key or len(key) > 128 or not validate_value(value):
            raise WebServiceError(
                    'Source search parameters must contain short names and '
                    'simple values.', 422)


def _local_host(host: str) -> bool:
    hostname = host.rsplit(':', 1)[0].strip('[]').lower()
    return hostname in {'127.0.0.1', 'localhost'}


def create_app() -> FastAPI:
    """Create an isolated application and single-user radio session."""
    directory.import_drivers()
    session = DriverSession()
    transfers = TransferManager(session)
    source_queries = SourceQueryManager(session)

    @asynccontextmanager
    async def lifespan(app):
        try:
            yield
        finally:
            source_queries.close()
            transfers.close()

    app = FastAPI(
            title='CHIRP Web Local Web',
            docs_url=None,
            redoc_url=None,
            openapi_url=None,
            lifespan=lifespan,
    )
    app.state.session = session
    app.state.transfers = transfers
    app.state.source_queries = source_queries

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
        tab_id = request.headers.get('x-chirp-tab')
        tab_token = None
        if (tab_id and request.url.path.startswith('/api/') and
                not request.url.path.startswith('/api/transfers/')):
            tab_token = session.use_tab(tab_id)
        live_mutations = (
            (request.url.path != '/api/memories/query' and
             request.url.path.startswith('/api/memories/')) or
            request.url.path in {
                '/api/settings', '/api/banks', '/api/sources/import',
                '/api/session/import',
            }
        )
        if (live_mutations and request.method in {'POST', 'PATCH'} and
                session.is_live() and
                request.headers.get('x-chirp-confirm-live') != 'true'):
            return JSONResponse(
                    {'detail': 'Confirm that this edit will be applied '
                               'immediately to the live radio.'},
                    status_code=409)
        try:
            response = await call_next(request)
        finally:
            if tab_token is not None:
                session.reset_tab(tab_token)
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

    @app.get('/api/radios/{radio_id}/prompts')
    def radio_prompts(radio_id: str):
        return transfers.prompts(radio_id)

    @app.get('/api/transfers/prompts/upload')
    def upload_prompts():
        return transfers.upload_prompts()

    @app.get('/api/ports')
    def list_ports():
        return transfers.ports()

    @app.get('/api/ports/baseline')
    def port_baseline():
        return {'ports': transfers.ports()}

    @app.get('/api/ports/detect')
    def detect_ports(baseline: str = Query(default='', max_length=8192)):
        try:
            previous = json.loads(baseline) if baseline else []
        except json.JSONDecodeError as exc:
            raise WebServiceError('Port baseline must be valid JSON.', 422) from exc
        if not isinstance(previous, list) or not all(
                isinstance(item, str) for item in previous):
            raise WebServiceError('Port baseline must be a list of paths.',
                                  422)
        ports = transfers.ports()
        known = set(previous)
        return {'ports': ports,
                'detected': [item for item in ports
                             if item['port'] not in known]}

    @app.get('/api/about')
    def about():
        try:
            version = metadata.version('chirp-web')
        except metadata.PackageNotFoundError:
            version = 'development'
        return {
            'version': version,
            'python': platform.python_version(),
            'platform': platform.platform(),
            'release_url': 'https://github.com/tmasterson/chirp-web/releases',
        }

    @app.get('/api/session')
    def get_session():
        return session.describe()

    @app.post('/api/session/close')
    def close_session():
        return session.close_tab()

    @app.get('/api/session/tabs')
    def get_tabs():
        return session.tabs_summary()

    @app.post('/api/session/tabs/{tab_id}/activate')
    def activate_tab(tab_id: str):
        return session.activate_tab(tab_id)

    @app.put('/api/session/tabs')
    def reorder_tabs(payload: TabOrder):
        return session.reorder_tabs(payload.tab_ids)

    @app.post('/api/session/subdevices/{index}')
    def select_subdevice(index: int):
        return session.select_subdevice(index)

    @app.get('/api/session/info')
    def get_radio_info():
        return session.radio_info()

    @app.get('/api/session/backups')
    def get_backups():
        return {'backups': session.backups()}

    @app.get('/api/session/backups/settings')
    def get_backup_settings():
        return session.backup_settings()

    @app.put('/api/session/backups/settings')
    def set_backup_settings(payload: BackupStorageSettings):
        return session.configure_backup_storage(
                payload.directory, payload.retention)

    @app.get('/api/session/backups/{backup_id}')
    def download_backup(backup_id: str):
        return FileResponse(
                session.backup_path(backup_id),
                filename=f'{backup_id}.img',
                media_type='application/octet-stream')

    @app.post('/api/session/backups/{backup_id}/restore')
    def restore_backup(backup_id: str):
        return session.restore_backup(backup_id)

    @app.delete('/api/session/backups/{backup_id}')
    def delete_backup(backup_id: str):
        return session.delete_backup(backup_id)

    @app.get('/api/session/diagnostics')
    def download_diagnostics():
        return Response(
                session.diagnostic_bundle(),
                media_type='application/zip',
                headers={'Content-Disposition':
                         'attachment; filename="chirp-web-diagnostics.zip"'})

    @app.get('/api/session/report-manifest')
    def get_report_manifest():
        return session.report_manifest()

    @app.post('/api/session/report')
    def download_support_report(payload: SupportReportRequest):
        return Response(
                session.support_report(payload.include),
                media_type='application/zip',
                headers={'Content-Disposition':
                         'attachment; filename="chirp-web-support.zip"'})

    @app.post('/api/session/recovery/export')
    def export_recovery():
        return session.recovery_export()

    @app.post('/api/session/recovery/import')
    def import_recovery(payload: RecoveryImport):
        return session.recovery_import(payload.tabs)

    @app.get('/api/configurations')
    def list_configurations():
        return session.configurations()

    @app.post('/api/session/new')
    def new_configuration(payload: NewConfiguration):
        return session.new_configuration(
                payload.template_id, payload.confirm_replace)

    @app.get('/api/session/history')
    def get_history():
        return session.history()

    @app.post('/api/session/undo')
    def undo():
        return session.undo()

    @app.post('/api/session/redo')
    def redo():
        return session.redo()

    @app.get('/api/bandplans')
    def get_bandplans():
        return session.bandplans()

    @app.patch('/api/bandplans')
    def set_bandplan(payload: BandplanUpdate):
        return session.set_bandplan(payload.name)

    @app.post('/api/bandplans/defaults')
    def get_frequency_defaults(payload: FrequencyDefaultsRequest):
        return session.frequency_defaults(payload.frequency)

    @app.get('/api/sources')
    def list_sources():
        return [
            {
                'id': source_id,
                'name': source['name'],
                'example': source['example'],
                'help': source['help'],
                'fields': source.get('fields', []),
            }
            for source_id, source in SOURCE_CATALOG.items()
        ]

    @app.post('/api/sources/{source_id}/query')
    def query_source(source_id: str, payload: SourceQuery):
        source = SOURCE_CATALOG.get(source_id)
        if source is None:
            raise WebServiceError('Unknown repeater source.', 404)
        _validate_source_params(payload.params)
        required = {
            'dmrmarc': ('city', 'state', 'country'),
            'radioreference': (
                'username', 'password', 'country', 'zipcounty'),
            'repeaterbook': ('country', 'service'),
        }.get(source_id, ())
        missing = [field for field in required if field not in payload.params]
        if missing:
            raise WebServiceError(
                    'Missing source search parameters: ' +
                    ', '.join(missing), 422)
        if any(not isinstance(payload.params[field], str)
               for field in required):
            raise WebServiceError(
                    'Required source search parameters must be text.', 422)
        if (source_id == 'radioreference' and
                payload.params['country'] not in ('US', 'CA')):
            raise WebServiceError(
                    'RadioReference country must be US or CA.', 422)
        params = dict(payload.params)
        return source_queries.start(
                source_id, source, params, session.active_tab_id)

    @app.get('/api/sources/jobs/{job_id}')
    def source_query_status(job_id: str):
        return source_queries.get(job_id)

    @app.delete('/api/sources/jobs/{job_id}')
    def cancel_source_query(job_id: str):
        return source_queries.cancel(job_id)

    @app.get('/api/sources/history')
    def source_history():
        return source_queries.history_summary()

    @app.post('/api/sources/history/{history_id}/retry')
    def retry_source_query(history_id: str):
        return source_queries.retry(
                history_id, SOURCE_CATALOG, session.active_tab_id)

    @app.post('/api/sources/import')
    def import_source_results(payload: SourceImport):
        try:
            return session.import_source_results(
                    payload.query_id, payload.selected)
        except WebServiceError as exc:
            if exc.status_code != 404:
                raise
            return source_queries.import_results(
                    payload.query_id, payload.selected)

    @app.post('/api/session/compare')
    def compare_image(payload: ImportImageRequest):
        try:
            return session.preview_image_memories(
                    payload.filename, payload.data_base64)
        except WebServiceError:
            raise
        except Exception as exc:
            LOG.exception('Unable to read source image for comparison')
            raise WebServiceError(
                    'The selected file could not be read as a radio image.',
                    422) from exc

    @app.post('/api/session/compare-tab')
    def compare_tab_memories(payload: TabMemoryCompare):
        numbers = [
            int(number) if isinstance(number, str) and number.isdecimal()
            else number for number in payload.numbers
        ]
        return session.compare_tab_memories(payload.tab_id, numbers)

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
    def list_memories(start: int | None = Query(default=None, ge=0),
                      limit: int = Query(default=50, ge=1, le=200),
                      search: str = Query(default='', max_length=200),
                      sort: str = Query(
                          default='number',
                          pattern='^(number|name|freq|mode|duplex)$'),
                      direction: str = Query(
                          default='asc', pattern='^(asc|desc)$'),
                      hide_empty: bool = False):
        details = session.describe()
        low, high = details['memory_bounds']
        filtered = bool(search or sort != 'number' or direction != 'asc' or
                        hide_empty)
        return session.memories(
                (0 if filtered else low) if start is None else start,
                limit, search, sort, direction, hide_empty)

    @app.post('/api/memories/query')
    def query_memories(payload: MemoryQuery):
        return session.memories(
                payload.start, payload.limit, sort=payload.sort,
                direction=payload.direction, hide_empty=payload.hide_empty,
                filters=[item.model_dump() for item in payload.filters],
                match=payload.match)

    @app.post('/api/memories/delete')
    def delete_memories(payload: MemoryDelete):
        numbers = [
            int(number) if isinstance(number, str) and number.isdecimal()
            else number for number in payload.numbers
        ]
        return session.delete_memories(numbers, payload.shift)

    @app.post('/api/memories/move')
    def move_memories(payload: MemoryMove):
        return session.move_memories(payload.numbers, payload.direction)

    @app.post('/api/memories/insert')
    def insert_memory(payload: MemoryInsert):
        return session.insert_memory_row(payload.number)

    @app.post('/api/memories/copy')
    def copy_memories(payload: MemoryCopy):
        numbers = [
            int(number) if isinstance(number, str) and number.isdecimal()
            else number for number in payload.numbers
        ]
        return session.copy_memories(numbers, cut=payload.cut)

    @app.post('/api/memories/paste')
    def paste_memories(payload: MemoryPaste):
        return session.paste_memories(
                payload.clipboard_id, payload.start, payload.overwrite)

    @app.patch('/api/memories/bulk')
    def bulk_update_memories(payload: MemoryBulkUpdate):
        numbers = [
            int(number) if isinstance(number, str) and number.isdecimal()
            else number for number in payload.numbers
        ]
        changes = payload.changes.model_dump(exclude_unset=True)
        extra_changes = changes.pop('extra_changes', None)
        if any(value is None for value in changes.values()):
            raise WebServiceError(
                    'Memory field values cannot be null.', 422)
        if extra_changes is None and not changes:
            raise WebServiceError('Provide at least one memory field.', 422)
        return session.bulk_update_memories(
                numbers, changes, extra_changes)

    @app.post('/api/memories/arrange')
    def arrange_memories(payload: MemoryArrange):
        return session.arrange_memories(
                payload.numbers, payload.operation,
                payload.field, payload.direction)

    @app.patch('/api/memories/{number}')
    def update_memory(number: str, payload: MemoryUpdate):
        number = int(number) if number.isdecimal() else number
        values = payload.model_dump(exclude_unset=True)
        extra_changes = values.pop('extra_changes', None)
        if any(value is None for value in values.values()):
            raise WebServiceError(
                    'Memory field values cannot be null.', 422)
        if extra_changes is None and not values:
            raise WebServiceError('Provide at least one memory field.', 422)
        return session.update_memory(number, values, extra_changes)

    @app.get('/api/banks')
    def list_banks():
        return session.bank_models()

    @app.patch('/api/memories/{number}/banks')
    def update_memory_bank_membership(
            number: str, payload: BankMembershipRequest):
        number = int(number) if number.isdecimal() else number
        return session.update_memory_bank_membership(
                number,
                payload.model,
                payload.bank_index,
                payload.enabled,
        )

    @app.patch('/api/banks')
    def update_bank(payload: BankUpdate):
        return session.update_bank(
                payload.model, payload.bank_index, payload.name,
                payload.memory_number, payload.index)

    @app.get('/api/settings')
    def get_settings():
        return session.radio_settings()

    @app.patch('/api/settings')
    def update_settings(payload: SettingsUpdate):
        return session.update_settings(
                [change.model_dump() for change in payload.changes],
                confirm_warnings=payload.confirm_warnings)

    @app.post('/api/session/save')
    def save_image(preserve_dirty: bool = False):
        try:
            return session.save_image(mark_clean=not preserve_dirty)
        except WebServiceError:
            raise
        except Exception as exc:
            LOG.exception('Unable to save radio image')
            raise WebServiceError(
                    'The radio driver could not save this image.',
                    500) from exc

    @app.get('/api/session/export.csv')
    def export_csv():
        return Response(
                session.export_csv(),
                media_type='text/csv',
                headers={'Content-Disposition':
                         'attachment; filename="channels.csv"'})

    @app.post('/api/session/export.csv')
    def export_scoped_csv(payload: MemoryScope):
        numbers = [
            int(number) if isinstance(number, str) and number.isdecimal()
            else number for number in payload.numbers
        ]
        return Response(
                session.export_csv(
                    payload.scope, numbers,
                    [item.model_dump() for item in payload.filters],
                    payload.match, payload.search, payload.sort,
                    payload.direction, payload.hide_empty),
                media_type='text/csv',
                headers={'Content-Disposition':
                         'attachment; filename="channels.csv"'})

    @app.post('/api/session/print')
    def print_memories(payload: MemoryScope):
        numbers = [
            int(number) if isinstance(number, str) and number.isdecimal()
            else number for number in payload.numbers
        ]
        return session.print_rows(
                payload.scope, numbers,
                [item.model_dump() for item in payload.filters],
                payload.match, payload.search, payload.sort,
                payload.direction, payload.hide_empty)

    @app.post('/api/session/import')
    def import_image(payload: ImportImageRequest):
        try:
            return session.import_image_memories(
                    payload.filename, payload.data_base64,
                    payload.placement, payload.destination_start)
        except WebServiceError:
            raise
        except Exception as exc:
            LOG.exception('Unable to merge memories from uploaded image')
            raise WebServiceError(
                    'The selected file could not be read as a radio image.',
                    422) from exc

    @app.post('/api/transfers/download')
    def download_radio(payload: DownloadRequest):
        return transfers.start(
                'download',
                payload.radio_id,
                payload.port,
                confirm_replace=payload.confirm_replace,
                confirm_prompts=payload.confirm_prompts)

    @app.post('/api/transfers/upload')
    def upload_radio(payload: UploadRequest):
        return transfers.start(
                'upload', '', payload.port, confirm=payload.confirm,
                confirm_prompts=payload.confirm_prompts)

    @app.get('/api/transfers/{job_id}')
    def transfer_status(job_id: str):
        return transfers.get(job_id)

    @app.delete('/api/transfers/{job_id}')
    def cancel_transfer(job_id: str):
        return transfers.cancel(job_id)

    return app


app = create_app()
