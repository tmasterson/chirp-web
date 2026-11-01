"""Session, source, and transfer discovery routes."""


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


import json
import platform
from importlib import metadata

from fastapi import Query
from fastapi.responses import FileResponse, Response

from chirp_web.webui.service import WebServiceError


def register_session_routes(app, session, transfers, source_queries,
                            source_catalog, validate_source_params, log):
    """Register non-memory API routes on an application."""
    from chirp_web.webui.api import (
            AdvancedDiagnosticsUpdate, BackupStorageSettings,
            BandplanUpdate, FrequencyDefaultsRequest, ImportImageRequest,
            NewConfiguration, OpenImageRequest, RecoveryImport,
            SourceImport, SourceQuery, SupportReportRequest, TabMemoryCompare,
            TabOrder)

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
            raise WebServiceError(
                    'Port baseline must be valid JSON.', 422) from exc
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

    @app.get('/api/session/transfer-trace')
    def get_transfer_trace():
        return session.transfer_trace()

    @app.get('/api/session/advanced-diagnostics')
    def advanced_diagnostics_state():
        return session.advanced_diagnostics_state()

    @app.patch('/api/session/advanced-diagnostics')
    def set_advanced_diagnostics(payload: AdvancedDiagnosticsUpdate):
        return session.set_advanced_diagnostics(payload.enabled)

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
            for source_id, source in source_catalog.items()
        ]

    @app.post('/api/sources/{source_id}/query')
    def query_source(source_id: str, payload: SourceQuery):
        source = source_catalog.get(source_id)
        if source is None:
            raise WebServiceError('Unknown repeater source.', 404)
        validate_source_params(payload.params)
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
                history_id, source_catalog, session.active_tab_id)

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
            log.exception('Unable to read source image for comparison')
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
            log.exception('Unable to open uploaded radio image')
            raise WebServiceError(
                    'The selected file could not be opened by a supported '
                    'radio driver.', 422) from exc
