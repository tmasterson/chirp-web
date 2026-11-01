"""Read-only diagnostics, backups, and recovery operations."""


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


import base64
import difflib
import io
import json
import shutil
import tempfile
import time
import uuid
import zipfile
from pathlib import Path

from chirp_web import chirp_common


class SessionDiagnostics:
    """Keep support and recovery concerns outside the editing session."""

    def __init__(self, session, error_type, log):
        self.session = session
        self.error_type = error_type
        self.log = log

    def radio_info(self):
        """Return safe, read-only identity and feature information."""
        with self.session.lock:
            radio = self.session._require_radio()
            features = radio.get_features()
            radio_class = getattr(radio, '_orig_rclass', radio.__class__)
            metadata = {
                str(key): str(value)
                for key, value in getattr(radio, 'metadata', {}).items()
                if key not in {'raw', 'mem_extra'}
            }
            return {
                'name': radio.get_name(),
                'driver': {
                    'class': radio_class.__name__,
                    'module': radio_class.__module__,
                },
                'image': {
                    'filename': self.session.source_name,
                    'metadata': metadata,
                },
                'features': {
                    key: (
                        [str(item) for item in getattr(features, key)]
                        if isinstance(getattr(features, key), list)
                        else str(getattr(features, key))
                    )
                    for key in features._valid_map
                },
            }

    def advanced_diagnostics_state(self):
        """Return whether the local user enabled raw diagnostic output."""
        with self.session.lock:
            return {'enabled': self.session.advanced_diagnostics}

    def set_advanced_diagnostics(self, enabled):
        """Explicitly enable or disable local, read-only raw diagnostics."""
        with self.session.lock:
            self.session.advanced_diagnostics = enabled
            return self.session.advanced_diagnostics_state()

    def raw_memories(self, numbers):
        """Return driver raw-memory text only after an explicit local
        opt-in."""
        with self.session.lock:
            self.session._ensure_idle()
            if not self.session.advanced_diagnostics:
                raise self.error_type(
                        'Enable advanced diagnostics before viewing raw '
                        'memory data.', 409)
            radio = self.session._require_radio()
            if not callable(getattr(radio, 'get_raw_memory', None)):
                raise self.error_type(
                        'This radio driver does not expose raw memory data.',
                        422)
            result = []
            for number in numbers:
                self.session._validate_memory_id(radio, number)
                try:
                    raw = str(radio.get_raw_memory(number))
                except Exception as exc:
                    raise self.error_type(
                            f'Unable to read raw memory {number}.',
                            422) from exc
                if len(raw) > 262144:
                    raise self.error_type(
                            f'Raw memory {number} is too large to display.',
                            422)
                result.append({'number': number, 'raw': raw})
            return result

    def raw_memory_diff(self, numbers):
        """Compare two opt-in raw-memory views without permitting writes."""
        if len(numbers) != 2:
            raise self.error_type(
                    'Select exactly two channels to compare raw memory.', 422)
        memories = self.session.raw_memories(numbers)
        return {
            'memories': memories,
            'diff': ''.join(difflib.unified_diff(
                memories[0]['raw'].splitlines(keepends=True),
                memories[1]['raw'].splitlines(keepends=True),
                fromfile=f'channel-{memories[0]["number"]}',
                tofile=f'channel-{memories[1]["number"]}',
            )),
        }

    def transfer_trace(self):
        """Return the existing payload-free serial activity trace."""
        with self.session.lock:
            self.session._require_radio()
            return {'entries': list(self.session._tab.serial_trace)}

    def create_backup(self, reason):
        """Save a local, temporary pre-transfer copy of a clone image."""
        with self.session.lock:
            radio = self.session._tab.radio
            if radio is None:
                raise self.error_type('Open a radio image before editing.',
                                      409)
            if not isinstance(radio, chirp_common.CloneModeRadio):
                return None
            suffix = Path(self.session.source_name).suffix or '.img'
            handle = tempfile.NamedTemporaryFile(
                    prefix=f'chirp-web-{reason}-', suffix=suffix,
                    delete=False)
            path = handle.name
            handle.close()
            try:
                radio.save_mmap(path)
            except Exception:
                Path(path).unlink(missing_ok=True)
                raise
            tab = self.session._tab
            tab.backup_paths.append(path)
            for expired in tab.backup_paths[:-10]:
                Path(expired).unlink(missing_ok=True)
            del tab.backup_paths[:-10]
            backup = {
                'id': Path(path).name,
                'reason': reason,
                'created_at': int(time.time()),
                'filename': self.session._safe_name(self.session.source_name),
            }
            if self.session._backups.directory is not None:
                retained_name = (
                    f'chirp-web-backup-{int(time.time())}-{uuid.uuid4().hex}-'
                    f'{self.session._safe_name(self.session.source_name)}')
                try:
                    shutil.copyfile(path,
                                    self.session._backups.directory /
                                    retained_name)
                    self.session._backups.prune()
                except OSError as exc:
                    self.log.exception('Unable to retain backup in %s',
                                       self.session._backups.directory)
                    backup['retention_error'] = str(exc)
            return backup

    def backups(self):
        with self.session.lock:
            return self.session._backups.entries(
                    self.session._tab.backup_paths, self.session.source_name,
                    self.session._safe_name)

    def backup_path(self, backup_id):
        with self.session.lock:
            return str(self.session._backups.find(
                    self.session._tab.backup_paths, backup_id))

    def restore_backup(self, backup_id):
        """Open a backup as an independent tab without replacing the
        current."""
        with self.session.lock:
            path = self.session._backups.find(
                    self.session._tab.backup_paths, backup_id)
            data = base64.b64encode(path.read_bytes()).decode('ascii')
            filename = path.name.split('-', 5)[-1]
        return self.session.open_image(filename, data, confirm_replace=True)

    def delete_backup(self, backup_id):
        """Delete an explicitly selected retained backup."""
        with self.session.lock:
            path = self.session._backups.find(
                    self.session._tab.backup_paths, backup_id)
            if not self.session._backups.is_retained(path):
                raise self.error_type(
                        'Temporary backups expire with this tab and cannot '
                        'be deleted individually.', 409)
            try:
                path.unlink()
            except OSError as exc:
                raise self.error_type(
                        'The retained backup could not be deleted.',
                        500) from exc
            return {'deleted': backup_id}

    def diagnostic_bundle(self):
        """Build a local support archive without radio image contents."""
        info = self.session.radio_info()
        payload = json.dumps(info, indent=2, sort_keys=True).encode('utf-8')
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('radio-info.json', payload)
            archive.writestr(
                    'serial-trace.txt',
                    '\n'.join(self.session._tab.serial_trace) + '\n')
            archive.writestr(
                    'README.txt',
                    'This archive contains radio identity and capability '
                    'metadata and a redacted serial activity trace. It does '
                    'not include channel data, settings, serial payloads, '
                    'or credentials.\n')
        return output.getvalue()

    def report_manifest(self):
        """List reviewable, privacy-preserving support-report attachments."""
        with self.session.lock:
            self.session._require_radio()
            return {'files': [
                {'id': 'radio-info', 'name': 'radio-info.json',
                 'description': 'Driver, image, and supported-feature data.',
                 'default': True},
                {'id': 'serial-trace', 'name': 'serial-trace.txt',
                 'description': 'Redacted transfer timing and byte counts.',
                 'default': True},
                {'id': 'backups', 'name': 'backup-list.json',
                 'description': 'Names of available local backups, not their '
                                'contents.',
                 'default': False},
            ]}

    def support_report(self, include):
        """Build only the user-selected safe diagnostic files."""
        allowed = {'radio-info', 'serial-trace', 'backups'}
        requested = set(include)
        if not requested or not requested <= allowed:
            raise self.error_type('Select one or more valid report files.',
                                  422)
        with self.session.lock:
            self.session._require_radio()
            output = io.BytesIO()
            with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
                if 'radio-info' in requested:
                    archive.writestr(
                            'radio-info.json',
                            json.dumps(self.session.radio_info(), indent=2,
                                       sort_keys=True))
                if 'serial-trace' in requested:
                    archive.writestr(
                            'serial-trace.txt',
                            '\n'.join(self.session._tab.serial_trace) + '\n')
                if 'backups' in requested:
                    archive.writestr(
                            'backup-list.json',
                            json.dumps(self.session.backups(), indent=2))
            return output.getvalue()

    def recovery_export(self):
        """Serialize eligible tabs for explicit browser download."""
        with self.session.lock:
            self.session._ensure_idle()
            original = self.session.active_tab_id
            tabs = []
            skipped = []
            for tab_id, tab in self.session.tabs.items():
                if tab.radio is None:
                    continue
                if isinstance(tab.radio, chirp_common.LiveRadio):
                    skipped.append(tab.source_name)
                    continue
                self.session.active_tab_id = tab_id
                snapshot = self.session.save_image(mark_clean=False)
                tabs.append(snapshot)
            self.session.active_tab_id = original
            return {'tabs': tabs, 'skipped': skipped}

    def recovery_import(self, snapshots):
        """Restore explicit browser-provided image snapshots as new tabs."""
        if not snapshots:
            raise self.error_type('Recovery file contains no tabs.', 422)
        opened = []
        for snapshot in snapshots:
            if not isinstance(snapshot, dict):
                raise self.error_type('Invalid recovery tab.', 422)
            filename = snapshot.get('filename')
            data = snapshot.get('data_base64')
            if not isinstance(filename, str) or not isinstance(data, str):
                raise self.error_type('Invalid recovery tab.', 422)
            opened.append(self.session.open_image(filename, data,
                                                  confirm_replace=True))
        return {'opened': len(opened),
                'active_tab_id': self.session.active_tab_id}
