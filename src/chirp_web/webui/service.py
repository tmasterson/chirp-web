"""Local radio and transfer state for the browser interface."""

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
import binascii
import copy
import contextvars
import csv
import io
import logging
import math
import re
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import TypedDict

from chirp_web import bandplan, chirp_common, directory, settings
from chirp_web.webui.backups import BackupStorage
from chirp_web.webui.diagnostics import SessionDiagnostics
from chirp_web.webui.memory_history import MemoryHistory
from chirp_web.webui.memory_operations import MemoryOperations


LOG = logging.getLogger(__name__)
MAX_IMAGE_SIZE = 20 * 1024 * 1024
CONFIGURATION_TEMPLATES = {
    'blank': ('Blank CSV image', ()),
    '2m-simplex': ('2 m simplex starter', (
        (146520000, '2M CALL', 'FM'),
        (146580000, '2M SIMPLEX', 'FM'),
    )),
    '70cm-simplex': ('70 cm simplex starter', (
        (446000000, '70CM CALL', 'FM'),
        (446500000, '70CM SIMPLEX', 'FM'),
    )),
}
STOCK_CONFIG_PACKAGE = 'chirp_web.stock_configs'
MEMORY_FIELDS = (
        'name', 'freq', 'mode', 'duplex', 'offset', 'tmode', 'rtone',
        'ctone', 'dtcs', 'rx_dtcs', 'dtcs_polarity', 'cross_mode',
        'tuning_step', 'skip', 'comment', 'power',
)


class RejectedSourceResult(TypedDict):
    index: int
    reason: str


class WebServiceError(Exception):
    """An expected request or radio-operation error."""

    def __init__(self, message: str, status_code: int = 400):
        """Create an HTTP-facing error with its response status."""
        super().__init__(message)
        self.status_code = status_code


class RedactedSerialTrace:
    """Record serial activity without retaining radio payload contents."""

    def __init__(self, pipe, trace):
        self._pipe = pipe
        self._trace = trace
        self._started = time.monotonic()

    def _record(self, direction, size):
        self._trace.append(
                f'{time.monotonic() - self._started:8.3f}s {direction} '
                f'{size} byte(s)')
        del self._trace[:-500]

    def read(self, size=1):
        data = self._pipe.read(size)
        self._record('read', len(data))
        return data

    def write(self, data):
        result = self._pipe.write(data)
        self._record('write', len(data))
        return result

    def __getattr__(self, name):
        return getattr(self._pipe, name)


@dataclass
class SessionTab:
    """All mutable state associated with one open image or live radio."""

    id: str
    radio: object | None = None
    source_name: str = ''
    temp_path: str | None = None
    dirty: bool = False
    source_results: dict = field(default_factory=dict)
    undo_stack: list = field(default_factory=list)
    redo_stack: list = field(default_factory=list)
    bandplan_name: str = 'north_america'
    clipboard_results: dict = field(default_factory=dict)
    live_port: object | None = None
    backup_paths: list[str] = field(default_factory=list)
    serial_trace: list[str] = field(default_factory=list)
    subdevice_index: int = 0


class DriverSession:
    """Own local radio/image tabs edited by this app process."""

    def __init__(self) -> None:
        """Initialize the server-owned image tabs."""
        self.lock = threading.RLock()
        self.tabs: dict[str, SessionTab] = {}
        self.active_tab_id: str | None = None
        self.request_tab_id = contextvars.ContextVar(
                'chirp_web_tab_id', default=None)
        self.active_job = None
        self._backups = BackupStorage(WebServiceError)
        self.advanced_diagnostics = False
        self._diagnostics = SessionDiagnostics(self, WebServiceError, LOG)
        self._memory_history = MemoryHistory(self, WebServiceError, LOG)
        self._memory_operations = MemoryOperations(self, WebServiceError)
        self._new_tab()

    @property
    def _tab(self):
        tab_id = self.request_tab_id.get() or self.active_tab_id
        if tab_id is None:
            raise WebServiceError('No active image tab.', 409)
        try:
            return self.tabs[tab_id]
        except KeyError as exc:
            raise WebServiceError('Image tab was not found.', 404) from exc

    def use_tab(self, tab_id):
        """Select one tab for the current HTTP request context."""
        with self.lock:
            if tab_id not in self.tabs:
                raise WebServiceError('Image tab was not found.', 404)
            return self.request_tab_id.set(tab_id)

    def reset_tab(self, token):
        """Restore the prior request-scoped tab selection."""
        self.request_tab_id.reset(token)

    def _new_tab(self):
        tab = SessionTab(str(uuid.uuid4()))
        self.tabs[tab.id] = tab
        self.active_tab_id = tab.id
        if self.request_tab_id.get() is not None:
            self.request_tab_id.set(tab.id)
        return tab

    def activate_tab(self, tab_id):
        with self.lock:
            self._ensure_idle()
            if tab_id not in self.tabs:
                raise WebServiceError('Image tab was not found.', 404)
            self.active_tab_id = tab_id
            if self.request_tab_id.get() is not None:
                self.request_tab_id.set(tab_id)
            return self.describe()

    def tabs_summary(self):
        with self.lock:
            selected = self.request_tab_id.get() or self.active_tab_id
            return {
                'active_tab_id': selected,
                'tabs': [{
                    'id': tab.id,
                    'name': tab.radio.get_name() if tab.radio else 'New tab',
                    'filename': tab.source_name or 'Untitled',
                    'dirty': tab.dirty,
                    'active': tab.id == selected,
                } for tab in self.tabs.values()],
            }

    def is_live(self):
        with self.lock:
            return bool(
                    self.active_tab_id and isinstance(
                        self._tab.radio, chirp_common.LiveRadio) and
                    self._tab.live_port is not None)

    def close_tab(self):
        with self.lock:
            self._ensure_idle()
            tab = self._tab
            self._release_tab(tab)
            del self.tabs[tab.id]
            if not self.tabs:
                self.active_tab_id = None
            else:
                self.active_tab_id = next(iter(self.tabs))
            if self.active_tab_id is not None:
                self.request_tab_id.set(self.active_tab_id)
            return self.tabs_summary()

    def reorder_tabs(self, tab_ids):
        """Persist a user-requested image-tab order without changing state."""
        with self.lock:
            if (len(tab_ids) != len(self.tabs) or
                    set(tab_ids) != set(self.tabs)):
                raise WebServiceError('The requested tab order is invalid.',
                                      422)
            self.tabs = {tab_id: self.tabs[tab_id] for tab_id in tab_ids}
            return self.tabs_summary()

    @property
    def radio(self):
        return self._selected_radio(self._tab)

    @radio.setter
    def radio(self, value):
        self._tab.radio = value
        self._tab.subdevice_index = 0

    @staticmethod
    def _subdevices(tab):
        if tab.radio is None or not tab.radio.get_features().has_sub_devices:
            return [tab.radio] if tab.radio is not None else []
        return list(tab.radio.get_sub_devices())

    def _selected_radio(self, tab):
        radios = self._subdevices(tab)
        if not radios:
            return None
        tab.subdevice_index = min(tab.subdevice_index, len(radios) - 1)
        return radios[tab.subdevice_index]

    def select_subdevice(self, index):
        """Select the module used by the current tab's editors."""
        with self.lock:
            self._ensure_idle()
            radios = self._subdevices(self._tab)
            if not radios:
                raise WebServiceError('Open a radio image first.', 409)
            if not 0 <= index < len(radios):
                raise WebServiceError(
                        'The selected radio module was not found.',
                        404)
            self._tab.subdevice_index = index
            return self.describe()

    @property
    def source_name(self):
        return self._tab.source_name

    @source_name.setter
    def source_name(self, value):
        self._tab.source_name = value

    @property
    def temp_path(self):
        return self._tab.temp_path

    @temp_path.setter
    def temp_path(self, value):
        self._tab.temp_path = value

    @property
    def dirty(self):
        return self._tab.dirty

    @dirty.setter
    def dirty(self, value):
        self._tab.dirty = value

    @property
    def source_results(self):
        return self._tab.source_results

    @property
    def undo_stack(self):
        return self._tab.undo_stack

    @undo_stack.setter
    def undo_stack(self, value):
        self._tab.undo_stack = value

    @property
    def redo_stack(self):
        return self._tab.redo_stack

    @redo_stack.setter
    def redo_stack(self, value):
        self._tab.redo_stack = value

    @property
    def bandplan_name(self):
        return self._tab.bandplan_name

    @bandplan_name.setter
    def bandplan_name(self, value):
        self._tab.bandplan_name = value

    @property
    def clipboard_results(self):
        return self._tab.clipboard_results

    def _record_memory_change(self, before, after):
        self._memory_history.record(before, after)

    def history(self):
        with self.lock:
            return self._memory_history.summary()

    def undo(self):
        return self._memory_history.undo()

    def redo(self):
        return self._memory_history.redo()

    def _require_radio(self):
        if self.radio is None:
            raise WebServiceError('Open a radio image before editing.', 409)
        return self.radio

    @staticmethod
    def _memory_id(memory):
        return memory.extd_number or memory.number

    @staticmethod
    def _empty_memory(number):
        memory = chirp_common.Memory()
        memory.empty = True
        if isinstance(number, str):
            memory.extd_number = number
        else:
            memory.number = number
        return memory

    @staticmethod
    def _memory_ids(radio):
        features = radio.get_features()
        low, high = features.memory_bounds
        return [
            *range(low, high + 1),
            *features.valid_special_chans,
        ]

    @staticmethod
    def _validate_memory_id(radio, number):
        if isinstance(number, bool):
            raise WebServiceError('Invalid channel identifier.', 422)
        features = radio.get_features()
        low, high = features.memory_bounds
        if isinstance(number, str):
            if number not in features.valid_special_chans:
                raise WebServiceError('Unknown special channel.', 422)
        elif not isinstance(number, int) or not low <= number <= high:
            raise WebServiceError(
                    f'Channel must be between {low} and {high}.', 422)
        return number

    @staticmethod
    def _safe_name(filename: str) -> str:
        name = filename.replace('\\', '/').rsplit('/', 1)[-1].strip()
        if not name or name in {'.', '..'}:
            return 'radio.img'
        name = re.sub(r'[^A-Za-z0-9._ -]', '_', name)[:128]
        if not Path(name).suffix:
            name += '.img'
        return name

    def open_image(self, filename: str, encoded: str,
                   confirm_replace: bool = False):
        """Decode and identify an uploaded radio image."""
        if len(encoded) > (MAX_IMAGE_SIZE * 4 // 3) + 8:
            raise WebServiceError('Image exceeds the 20 MiB size limit.', 413)
        try:
            data = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise WebServiceError('Image data is not valid base64.') from exc
        if not data:
            raise WebServiceError('The selected image is empty.')
        if len(data) > MAX_IMAGE_SIZE:
            raise WebServiceError('Image exceeds the 20 MiB size limit.', 413)

        safe_name = self._safe_name(filename)
        suffix = Path(safe_name).suffix[:16] or '.img'
        with self.lock:
            self._ensure_idle()
            if self.active_tab_id is None:
                self._new_tab()
            if self.dirty and not confirm_replace:
                raise WebServiceError(
                        'Confirm that you want to keep editing this image '
                        'in a separate tab.', 409)
            handle = tempfile.NamedTemporaryFile(
                    prefix='chirp-web-', suffix=suffix, delete=False)
            new_path = handle.name
            try:
                with handle:
                    handle.write(data)
                radio = directory.get_radio_by_image(new_path)
            except Exception:
                Path(new_path).unlink(missing_ok=True)
                raise
            if self.radio is not None:
                self._new_tab()
            self._replace_radio(radio, safe_name, new_path)
        return self.describe()

    def _replace_radio(self, radio, filename, temp_path):
        old_path = self.temp_path
        self.radio = radio
        self.source_name = filename
        self.temp_path = temp_path
        self.dirty = False
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.source_results.clear()
        self.clipboard_results.clear()
        if old_path and old_path != temp_path:
            Path(old_path).unlink(missing_ok=True)

    @staticmethod
    def _close_port(port):
        try:
            if port is not None and port.is_open:
                port.close()
        except Exception:
            LOG.exception('Unable to close live radio serial port')

    def _release_tab(self, tab):
        self._close_port(tab.live_port)
        if tab.temp_path:
            Path(tab.temp_path).unlink(missing_ok=True)
        for path in tab.backup_paths:
            Path(path).unlink(missing_ok=True)

    def backup_settings(self):
        """Return the optional local directory used for retained backups."""
        with self.lock:
            return self._backups.settings()

    def configure_backup_storage(self, directory, retention):
        """Configure explicitly requested on-disk backup retention."""
        with self.lock:
            return self._backups.configure(directory, retention)

    def configurations(self):
        """Return built-in and bundled desktop configuration templates."""
        templates = [
            {'id': template_id, 'name': name}
            for template_id, (name, _) in CONFIGURATION_TEMPLATES.items()
        ]
        templates.extend(
            {'id': item.name, 'name': item.name.removesuffix('.csv')}
            for item in sorted(
                resources.files(STOCK_CONFIG_PACKAGE).iterdir(),
                key=lambda resource: resource.name.casefold())
            if item.is_file() and item.name.lower().endswith('.csv')
        )
        return templates

    def new_configuration(self, template_id: str, confirm_replace=False):
        """Create a fresh CSV image or one of the packaged starter layouts."""
        with self.lock:
            self._ensure_idle()
            if self.active_tab_id is None:
                self._new_tab()
            builtin = CONFIGURATION_TEMPLATES.get(template_id)
            stock_file = next((
                item for item in resources.files(
                    STOCK_CONFIG_PACKAGE).iterdir()
                if item.is_file() and item.name == template_id
            ), None)
            if builtin is None and stock_file is None:
                raise WebServiceError('Unknown configuration template.', 404)
            if self.dirty and not confirm_replace:
                raise WebServiceError(
                        'Confirm that you want to keep editing this image '
                        'in a separate tab.', 409)
            csv_class = directory.get_radio('Generic_CSV')
            handle = tempfile.NamedTemporaryFile(
                    prefix='chirp-web-new-', suffix='.csv', delete=False)
            temp_path = handle.name
            handle.close()
            Path(temp_path).unlink(missing_ok=True)
            try:
                if stock_file is not None:
                    Path(temp_path).write_bytes(stock_file.read_bytes())
                    radio = csv_class(temp_path)
                else:
                    radio = csv_class(temp_path)
                    first = chirp_common.Memory(number=0)
                    first.empty = True
                    radio.set_memory(first)
                    for number, (frequency, name, mode) in enumerate(
                            builtin[1], start=1):
                        memory = chirp_common.Memory(number=number)
                        memory.freq = frequency
                        memory.name = name
                        memory.mode = mode
                        memory.empty = False
                        radio.set_memory(memory)
            except Exception:
                Path(temp_path).unlink(missing_ok=True)
                raise
            filename = stock_file.name if stock_file else f'{template_id}.csv'
            if self.radio is not None:
                self._new_tab()
            self._replace_radio(radio, filename, temp_path)
            return self.describe()

    def _ensure_idle(self):
        if self.active_job:
            raise WebServiceError(
                    'Wait for the active radio transfer to finish.', 409)

    @staticmethod
    def _bank_model_summary(model):
        """Serialize a radio mapping model for the browser."""
        try:
            mappings = list(model.get_mappings())
        except NotImplementedError:
            mappings = []
        can_index = isinstance(
                model, chirp_common.MappingModelIndexInterface)
        return {
            'name': model.get_name(),
            'count': model.get_num_mappings(),
            'can_index': can_index,
            'index_bounds': (
                list(model.get_index_bounds())
                if can_index
                else None
            ),
            'mappings': [
                {
                    'index': mapping.get_index(),
                    'name': mapping.get_name(),
                    'can_rename': callable(
                        getattr(mapping, 'set_name', None)),
                    'positions': (
                        {
                            str(memory.number): model.get_memory_index(
                                memory, mapping)
                            for memory in model.get_mapping_memories(mapping)
                        }
                        if can_index else {}
                    ),
                    'members': sorted(
                        memory.number for memory in
                        model.get_mapping_memories(mapping)
                    ),
                }
                for mapping in mappings
            ],
        }

    def describe(self):
        """Return the open radio's identity and supported memory features."""
        with self.lock:
            radio = self._require_radio()
            parent_radio = self._tab.radio
            rf = radio.get_features()
            return {
                'tab_id': self._tab.id,
                'name': radio.get_name(),
                'filename': self.source_name,
                'dirty': self.dirty,
                'supports_upload': isinstance(
                        parent_radio, chirp_common.CloneModeRadio),
                'is_live': isinstance(parent_radio, chirp_common.LiveRadio),
                'has_settings': rf.has_settings,
                'memory_bounds': list(rf.memory_bounds),
                'valid_special_chans': list(rf.valid_special_chans),
                'subdevices': [
                    {'index': index, 'name': child.get_name()}
                    for index, child in enumerate(self._subdevices(self._tab))
                ],
                'selected_subdevice': self._tab.subdevice_index,
                'bank_models': [
                    self._bank_model_summary(model)
                    for model in radio.get_mapping_models()
                ],
                'features': {
                    'has_name': rf.has_name,
                    'valid_name_length': rf.valid_name_length,
                    'has_mode': rf.has_mode,
                    'has_offset': rf.has_offset,
                    'has_tuning_step': rf.has_tuning_step,
                    'has_ctone': rf.has_ctone,
                    'has_dtcs': rf.has_dtcs,
                    'has_rx_dtcs': rf.has_rx_dtcs,
                    'has_dtcs_polarity': rf.has_dtcs_polarity,
                    'has_cross': rf.has_cross,
                    'has_comment': rf.has_comment,
                    'has_variable_power': rf.has_variable_power,
                    'valid_power_levels': [
                        {'value': self._power_watts(level),
                         'label': str(level)}
                        for level in rf.valid_power_levels
                    ],
                    'has_bank_index': rf.has_bank_index,
                    'has_bank_names': rf.has_bank_names,
                    'bandplans': self.bandplans()['plans'],
                    'bandplan': self.bandplan_name,
                    'can_delete': rf.can_delete,
                    'valid_modes': list(rf.valid_modes),
                    'valid_duplexes': list(rf.valid_duplexes),
                    'valid_tmodes': list(rf.valid_tmodes),
                    'valid_tones': list(rf.valid_tones),
                    'valid_dtcs_codes': list(rf.valid_dtcs_codes),
                    'valid_dtcs_pols': list(rf.valid_dtcs_pols),
                    'valid_cross_modes': list(rf.valid_cross_modes),
                    'valid_tuning_steps': list(rf.valid_tuning_steps),
                    'valid_skips': list(rf.valid_skips),
                },
            }

    def radio_info(self):
        return self._diagnostics.radio_info()

    def advanced_diagnostics_state(self):
        return self._diagnostics.advanced_diagnostics_state()

    def set_advanced_diagnostics(self, enabled):
        return self._diagnostics.set_advanced_diagnostics(enabled)

    def raw_memories(self, numbers):
        return self._diagnostics.raw_memories(numbers)

    def raw_memory_diff(self, numbers):
        return self._diagnostics.raw_memory_diff(numbers)

    def transfer_trace(self):
        return self._diagnostics.transfer_trace()

    def create_backup(self, reason):
        return self._diagnostics.create_backup(reason)

    def backups(self):
        return self._diagnostics.backups()

    def backup_path(self, backup_id):
        return self._diagnostics.backup_path(backup_id)

    def restore_backup(self, backup_id):
        return self._diagnostics.restore_backup(backup_id)

    def delete_backup(self, backup_id):
        return self._diagnostics.delete_backup(backup_id)

    def diagnostic_bundle(self):
        return self._diagnostics.diagnostic_bundle()

    def report_manifest(self):
        return self._diagnostics.report_manifest()

    def support_report(self, include):
        return self._diagnostics.support_report(include)

    def recovery_export(self):
        return self._diagnostics.recovery_export()

    def recovery_import(self, snapshots):
        return self._diagnostics.recovery_import(snapshots)

    @staticmethod
    def _settings_tree(radio_settings):
        """Serialize supported driver settings for the browser editor."""
        groups = (radio_settings if isinstance(
                radio_settings, settings.RadioSettings) else
                  [radio_settings])

        def scalar_value(value, path, label, description, warning=None):
            result = {
                'path': path,
                'label': label,
                'description': description,
                'mutable': value.get_mutable(),
                'warning': warning,
            }
            if isinstance(value, settings.RadioSettingValueBoolean):
                result.update(type='boolean', value=bool(value))
            elif isinstance(value, settings.RadioSettingValueInteger):
                result.update(
                        type='integer', value=int(value),
                        min=value.get_min(), max=value.get_max(),
                        step=value.get_step())
            elif isinstance(value, settings.RadioSettingValueFloat):
                result.update(
                        type='float', value=float(value),
                        min=value.get_min(), max=value.get_max())
            elif isinstance(value, settings.RadioSettingValueList):
                result.update(
                        type='list', value=value.get_value(),
                        options=value.get_options())
            elif isinstance(value, settings.RadioSettingValueString):
                result.update(
                        type='string', value=str(value).rstrip(),
                        max=value.maxlength)
            else:
                raise WebServiceError(
                        f'Unsupported radio setting type: '
                        f'{type(value).__name__}.', 422)
            return result

        def serialize(element, path):
            if isinstance(element, settings.RadioSetting):
                label = element.get_shortname()
                description = str(element.__doc__ or '')
                values = element.value
                if not isinstance(values, list):
                    warning = element.get_warning(values.get_value())
                    return scalar_value(
                            values, path, label, description, warning)
                children = []
                for index, value in enumerate(values):
                    child_path = path + [index]
                    children.append(scalar_value(
                            value, child_path,
                            f'{label} {index + 1}', description))
                return {
                    'type': 'group', 'label': label,
                    'description': description, 'children': children,
                }
            if isinstance(element, settings.RadioSettingGroup):
                return {
                    'type': 'group',
                    'label': element.get_shortname(),
                    'description': str(element.__doc__ or ''),
                    'children': [
                        serialize(child, path + [child.get_name()])
                        for child in element
                    ],
                }
            raise WebServiceError(
                    'The radio driver returned an invalid settings tree.',
                    422)

        return [serialize(group, [group.get_name()]) for group in groups]

    @staticmethod
    def _valid_settings_tree(radio_settings):
        return isinstance(
                radio_settings,
                (settings.RadioSettings, settings.RadioSettingGroup))

    @staticmethod
    def _find_setting_value(radio_settings, path):
        """Resolve a browser setting path to its typed driver value."""
        if not path:
            raise WebServiceError('A setting path is required.', 422)
        element = None
        remaining = list(path)
        first = remaining.pop(0)
        groups = (radio_settings if isinstance(
                radio_settings, settings.RadioSettings) else
                  [radio_settings])
        element = next((item for item in groups
                        if isinstance(item, settings.RadioSettingGroup) and
                        item.get_name() == first), None)
        if element is None:
            raise WebServiceError('The selected radio setting was not found.',
                                  422)
        owner = None
        while remaining:
            part = remaining.pop(0)
            if isinstance(element, settings.RadioSettingGroup):
                if not isinstance(part, str) or part not in element:
                    raise WebServiceError(
                            'The selected radio setting was not found.',
                            422)
                element = element[part]
            elif isinstance(element, settings.RadioSetting):
                owner = element
                if not isinstance(part, int) or isinstance(part, bool):
                    raise WebServiceError(
                            'The selected radio setting value was not found.',
                            422)
                try:
                    element = element[part]
                except IndexError as exc:
                    raise WebServiceError(
                            'The selected radio setting value was not found.',
                            422) from exc
            else:
                raise WebServiceError('Invalid radio setting path.', 422)
        if isinstance(element, settings.RadioSetting):
            owner = element
            if len(element) != 1:
                raise WebServiceError(
                        'The selected radio setting requires a value index.',
                        422)
            element = element[0]
        if not isinstance(element, settings.RadioSettingValue):
            raise WebServiceError('Invalid radio setting path.', 422)
        return element, owner

    def radio_settings(self):
        """Return editable general settings from the active radio driver."""
        with self.lock:
            self._ensure_idle()
            radio = self._require_radio()
            if not radio.get_features().has_settings:
                return {'supported': False, 'groups': []}
            radio_settings = radio.get_settings()
            if not self._valid_settings_tree(radio_settings):
                raise WebServiceError(
                        'The radio driver did not provide usable settings.',
                        422)
            return {
                'supported': True,
                'groups': self._settings_tree(radio_settings),
            }

    def update_settings(self, changes, confirm_warnings=False):
        """Apply validated general setting changes through the radio driver."""
        with self.lock:
            self._ensure_idle()
            radio = self._require_radio()
            if not radio.get_features().has_settings:
                raise WebServiceError(
                        'This radio does not support general settings.', 422)
            radio_settings = radio.get_settings()
            if not self._valid_settings_tree(radio_settings):
                raise WebServiceError(
                        'The radio driver did not provide usable settings.',
                        422)
            if not changes:
                raise WebServiceError('Provide at least one setting change.')

            resolved = []
            seen = set()
            warnings = []
            for change in changes:
                path = change['path']
                key = tuple(path)
                if key in seen:
                    raise WebServiceError(
                            'A setting can only be changed once per request.',
                            422)
                seen.add(key)
                value, owner = self._find_setting_value(
                        radio_settings, path)
                requested = change['value']
                if isinstance(value, settings.RadioSettingValueBoolean):
                    valid_type = type(requested) is bool
                elif isinstance(value, settings.RadioSettingValueInteger):
                    valid_type = type(requested) is int
                elif isinstance(value, settings.RadioSettingValueFloat):
                    valid_type = type(requested) in (int, float)
                elif isinstance(value, settings.RadioSettingValueList):
                    valid_type = type(requested) in (str, int)
                elif isinstance(value, settings.RadioSettingValueString):
                    valid_type = type(requested) is str
                else:
                    raise WebServiceError(
                            'This radio setting cannot be edited.', 422)
                if not valid_type:
                    raise WebServiceError(
                            'The value type does not match this setting.',
                            422)
                try:
                    value.set_value(requested)
                except (settings.InvalidValueError, ValueError,
                        TypeError) as exc:
                    raise WebServiceError(str(exc), 422) from exc
                warning = owner.get_warning(value.get_value())
                if warning:
                    warnings.append(str(warning))
                resolved.append(value)

            if warnings and not confirm_warnings:
                raise WebServiceError(
                        'Radio setting warning: ' + '; '.join(warnings) +
                        ' Confirm to apply this change.', 409)
            radio.set_settings(radio_settings)
            self.dirty = True
            return {'warnings': warnings}

    def memories(self, start: int, limit: int, search: str = '',
                 sort: str = 'number', direction: str = 'asc',
                 hide_empty: bool = False, filters=None, match='all'):
        """Read a bounded range of memories from the open image."""
        with self.lock:
            self._ensure_idle()
            radio = self._require_radio()
            features = radio.get_features()
            low, high = features.memory_bounds
            if (search or sort != 'number' or direction != 'asc' or
                    hide_empty or filters):
                rows = [
                    self._memory_dict(radio.get_memory(number))
                    for number in self._memory_ids(radio)
                ]
                if hide_empty:
                    rows = [row for row in rows if not row['empty']]
                if search:
                    needle = search.casefold()
                    rows = [
                        row for row in rows
                        if not row['empty'] and any(
                            needle in str(row[field] or '').casefold()
                            for field in ('name', 'mode', 'duplex', 'tmode',
                                          'comment')
                        ) or (
                            not row['empty'] and
                            needle in chirp_common.format_freq(row['freq'])
                        )
                    ]
                if filters:
                    if match not in ('all', 'any'):
                        raise WebServiceError(
                                'Invalid filter match mode.', 422)

                    def filter_match(row, item):
                        field = item['field']
                        operator = item['operator']
                        value = item['value']
                        candidate = row[field]
                        if operator == 'contains':
                            if not isinstance(value, str):
                                raise WebServiceError(
                                        'Contains filters require text.', 422)
                            return value.casefold() in str(
                                    candidate or '').casefold()
                        if operator == 'matches':
                            if not isinstance(value, str) or len(value) > 128:
                                raise WebServiceError(
                                        'Regex filters require short text.',
                                        422)
                            try:
                                return bool(re.search(
                                        value, str(candidate or ''),
                                        re.IGNORECASE))
                            except re.error as exc:
                                raise WebServiceError(
                                        'Invalid regular expression.', 422
                                ) from exc
                        if operator == 'in':
                            if not isinstance(value, list) or not value:
                                raise WebServiceError(
                                        'In filters require one or more '
                                        'values.', 422)
                            return candidate in value or str(candidate) in {
                                    str(item) for item in value}
                        if operator == 'range':
                            if (not isinstance(value, list) or len(value) != 2
                                    or not all(
                                        isinstance(item, (int, float))
                                        for item in value)):
                                raise WebServiceError(
                                        'Range filters require two numbers.',
                                        422)
                            return value[0] <= (candidate or 0) <= value[1]
                        if operator == 'equals':
                            return candidate == value or str(candidate) == str(
                                    value)
                        raise WebServiceError('Unknown filter operator.', 422)

                    rows = [
                        row for row in rows if not row['empty'] and (
                            all(filter_match(row, item) for item in filters)
                            if match == 'all' else
                            any(filter_match(row, item) for item in filters)
                        )
                    ]

                def sort_value(row):
                    if sort == 'number':
                        value = row['number']
                        return ((0, value) if isinstance(value, int)
                                else (1, value))
                    if sort == 'freq':
                        return row['freq'] or 0
                    return str(row[sort] or '').casefold()

                rows.sort(
                        key=lambda row: (
                            sort_value(row), str(row['number'])),
                        reverse=direction == 'desc')
                rows.sort(key=lambda row: row['empty'])
                total = len(rows)
                page = rows[start:start + limit]
                return {
                    'start': start,
                    'end': start + len(page),
                    'total': total,
                    'memories': page,
                }
            ids = self._memory_ids(radio)
            start_index = max(0, start - low)
            rows = [
                self._memory_dict(radio.get_memory(number))
                for number in ids[start_index:start_index + limit]
            ]
            return {'start': start, 'end': start + len(rows),
                    'total': len(ids),
                    'memories': rows}

    def delete_memories(self, numbers: list[int | str], shift=''):
        return self._memory_operations.delete_memories(numbers, shift)

    def move_memories(self, numbers: list[int], direction: str):
        return self._memory_operations.move_memories(numbers, direction)

    def insert_memory_row(self, number: int):
        return self._memory_operations.insert_memory_row(number)

    def copy_memories(self, numbers: list[int | str], cut=False):
        return self._memory_operations.copy_memories(numbers, cut)

    def paste_memories(self, token: str, start: int, overwrite=False):
        return self._memory_operations.paste_memories(token, start, overwrite)

    def update_memory(self, number: int | str, values: dict,
                      extra_changes=None):
        return self._memory_operations.update_memory(
                number, values, extra_changes)

    def bulk_update_memories(self, numbers, values, extra_changes=None):
        return self._memory_operations.bulk_update_memories(
                numbers, values, extra_changes)

    def arrange_memories(self, numbers, operation, field='name',
                         direction='asc'):
        return self._memory_operations.arrange_memories(
                numbers, operation, field, direction)

    class _BandplanConfig:
        def __init__(self, selected):
            self.selected = selected

        def get(self, key, section):
            return None

        def set_bool(self, key, value, section):
            if value:
                self.selected = key

        def remove_option(self, key, section):
            return None

        def is_defined(self, key, section):
            return key in (
                'north_america', 'australia', 'iaru_r1', 'iaru_r2',
                'iaru_r3')

        def get_bool(self, key, section):
            return key == self.selected

    def _bandplans(self):
        return bandplan.BandPlans(
                self._BandplanConfig(self.bandplan_name))

    def bandplans(self):
        """List available bandplans and the current frequency helper."""
        with self.lock:
            plans = self._bandplans()
            return {
                'selected': self.bandplan_name,
                'plans': [
                    {'id': key, 'name': details[0]}
                    for key, details in plans.plans.items()
                ],
            }

    def set_bandplan(self, name):
        """Select the bandplan used by frequency-default lookups."""
        with self.lock:
            plans = self._bandplans()
            if name not in plans.plans:
                raise WebServiceError(
                        'The selected bandplan is unknown.', 422)
            self.bandplan_name = name
            return self.bandplans()

    def frequency_defaults(self, frequency):
        """Return the suggested settings for a frequency in MHz."""
        with self.lock:
            if (isinstance(frequency, bool) or
                    not isinstance(frequency, (int, float)) or
                    not math.isfinite(frequency) or frequency <= 0):
                raise WebServiceError(
                        'Enter a valid frequency in MHz.', 422)
            defaults = self._bandplans().get_defaults_for_frequency(
                    round(frequency * 1_000_000))
            return {
                'name': defaults.name,
                'mode': defaults.mode,
                'tuning_step': defaults.step_khz,
                'duplex': defaults.duplex,
                'offset': abs(defaults.offset or 0),
                'tones': list(defaults.tones or []),
            }

    def bank_models(self):
        """Return all active mapping models (such as bank models)."""
        with self.lock:
            self._ensure_idle()
            radio = self._require_radio()
            models = radio.get_mapping_models()
            return {
                'supported': bool(models),
                'models': [
                    self._bank_model_summary(model)
                    for model in models
                ],
            }

    def update_memory_bank_membership(self, number, model_name, bank_index,
                                      enabled):
        """Toggle a memory's membership in one bank mapping."""
        with self.lock:
            self._ensure_idle()
            radio = self._require_radio()
            if type(number) is not int:
                raise WebServiceError(
                        'Special channels cannot be assigned to banks.',
                        422)
            models = radio.get_mapping_models()
            if not models:
                raise WebServiceError(
                        'This radio does not expose any bank models.', 422)
            if not model_name:
                if len(models) != 1:
                    raise WebServiceError(
                            'Choose a bank model before updating membership.',
                            422)
                model = models[0]
            else:
                model = next((item for item in models
                              if item.get_name() == model_name), None)
                if model is None:
                    raise WebServiceError(
                            'The selected bank model was not found.', 422)

            mappings = list(model.get_mappings())
            if not mappings:
                raise WebServiceError(
                        'The selected bank model has no mappings.', 422)
            selected = next((mapping for mapping in mappings
                             if str(mapping.get_index()) == str(bank_index)),
                            None)
            if selected is None:
                try:
                    selected = mappings[int(bank_index)]
                except (TypeError, ValueError, IndexError) as exc:
                    raise WebServiceError(
                            'The selected bank was not found.', 422) from exc

            memory = radio.get_memory(number)
            if enabled:
                model.add_memory_to_mapping(memory, selected)
            else:
                model.remove_memory_from_mapping(memory, selected)
            self.dirty = True
            return {'memory': self._memory_dict(radio.get_memory(number)),
                    'model': model.get_name(),
                    'bank': {
                        'index': selected.get_index(),
                        'name': selected.get_name(),
                    },
                    'enabled': enabled}

    def update_bank(self, model_name, bank_index, name,
                    memory_number, index):
        """Rename a bank or change a memory's bank position."""
        with self.lock:
            self._ensure_idle()
            radio = self._require_radio()
            model = next((item for item in radio.get_mapping_models()
                          if item.get_name() == model_name), None)
            if model is None:
                raise WebServiceError('The selected bank model was not found.',
                                      404)
            mapping = next((item for item in model.get_mappings()
                            if str(item.get_index()) == str(bank_index)),
                           None)
            if mapping is None:
                raise WebServiceError('The selected bank was not found.',
                                      404)
            if name is not None:
                if memory_number is not None or index is not None:
                    raise WebServiceError(
                            'Choose either renaming or reordering.', 422)
                rename = getattr(mapping, 'set_name', None)
                if not callable(rename):
                    raise WebServiceError(
                            'This radio does not support bank names.', 422)
                if not name.strip():
                    raise WebServiceError(
                            'Bank names cannot be empty.', 422)
                rename(name.strip())
            elif memory_number is not None and index is not None:
                if not isinstance(
                        model, chirp_common.MappingModelIndexInterface):
                    raise WebServiceError(
                            'This radio does not support bank indices.', 422)
                low, high = model.get_index_bounds()
                if not low <= index <= high:
                    raise WebServiceError(
                            f'Bank index must be between {low} and {high}.',
                            422)
                memory_low, memory_high = radio.get_features().memory_bounds
                if not memory_low <= memory_number <= memory_high:
                    raise WebServiceError(
                            'The selected channel is outside the memory '
                            'range.', 422)
                memory = radio.get_memory(memory_number)
                if memory.empty:
                    raise WebServiceError(
                            'An empty channel cannot be indexed.', 422)
                model.set_memory_index(memory, mapping, index)
            else:
                raise WebServiceError(
                        'Provide either a bank name or memory index.', 422)
            self.dirty = True
            return self._bank_model_summary(model)

    def remember_source_results(self, memories):
        """Keep query results server-side for selected imports."""
        token = str(uuid.uuid4())
        with self.lock:
            self.source_results.clear()
            self.source_results[token] = memories
        return token

    def import_source_results(self, token: str, selected: list[int]):
        """Copy selected source memories into empty slots in the open image."""
        with self.lock:
            source_memories = self.source_results.get(token)
            if source_memories is None:
                raise WebServiceError('Source results have expired.', 404)
            if not selected:
                raise WebServiceError('Select at least one repeater.', 422)
            if len(selected) != len(set(selected)):
                raise WebServiceError(
                        'A source result can only be selected once.', 422)
            if any(index < 0 or index >= len(source_memories)
                   for index in selected):
                raise WebServiceError(
                        'A selected source result was not found.', 422)
            result = self._import_memories(
                    [source_memories[index] for index in selected])
            del self.source_results[token]
            return result

    def import_image_memories(self, filename: str, encoded: str,
                              placement='empty', destination_start=None):
        """Import memories from an uploaded image using an explicit policy."""
        memories = self._decode_image_memories(filename, encoded)
        if not memories:
            raise WebServiceError(
                    'The selected file contains no memories.', 422)
        result = self._import_memories(
                memories, placement=placement,
                destination_start=destination_start)
        result['source_count'] = len(memories)
        return result

    def preview_image_memories(self, filename: str, encoded: str):
        """Load another image for selected channel copying."""
        memories = self._decode_image_memories(filename, encoded)
        if not memories:
            raise WebServiceError(
                    'The selected file contains no memories.', 422)
        token = self.remember_source_results(memories)
        return {
            'query_id': token,
            'count': len(memories),
            'memories': [
                {**self._memory_dict(memory), 'number': index}
                for index, memory in enumerate(memories)
            ],
        }

    def compare_tab_memories(self, tab_id, numbers):
        """Return changed fields for selected channels in another open tab."""
        with self.lock:
            self._ensure_idle()
            current = self._require_radio()
            other_tab = self.tabs.get(tab_id)
            if other_tab is None:
                raise WebServiceError('Comparison image tab was not found.',
                                      404)
            if other_tab is self._tab:
                raise WebServiceError(
                        'Choose a different image tab for comparison.', 422)
            other = self._selected_radio(other_tab)
            if other is None:
                raise WebServiceError('Comparison image is not open.', 409)
            if not numbers or len(numbers) != len(set(numbers)):
                raise WebServiceError(
                        'Select one or more unique channels to compare.', 422)
            other_low, other_high = other.get_features().memory_bounds
            comparisons = []
            fields = ('empty', *MEMORY_FIELDS)
            for number in numbers:
                self._validate_memory_id(current, number)
                left = self._memory_dict(current.get_memory(number))
                if (not isinstance(number, int) or
                        not other_low <= number <= other_high):
                    right = None
                else:
                    right = self._memory_dict(other.get_memory(number))
                changes = {
                    field: {
                        'current': left[field],
                        'other': right[field] if right is not None else None,
                    }
                    for field in fields
                    if right is None or left[field] != right[field]
                }
                comparisons.append({
                    'number': number,
                    'equal': not changes,
                    'changes': changes,
                })
            return {
                'tab_id': tab_id,
                'filename': other_tab.source_name,
                'comparisons': comparisons,
            }

    def _decode_image_memories(self, filename: str, encoded: str):
        """Decode a radio image and return its programmed memories."""
        if len(encoded) > (MAX_IMAGE_SIZE * 4 // 3) + 8:
            raise WebServiceError('Image exceeds the 20 MiB size limit.', 413)
        try:
            data = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise WebServiceError('Image data is not valid base64.') from exc
        if not data:
            raise WebServiceError('The selected image is empty.')
        if len(data) > MAX_IMAGE_SIZE:
            raise WebServiceError('Image exceeds the 20 MiB size limit.', 413)

        suffix = Path(self._safe_name(filename)).suffix[:16] or '.img'
        with self.lock:
            self._ensure_idle()
            self._require_radio()
            handle = tempfile.NamedTemporaryFile(
                    prefix='chirp-web-import-', suffix=suffix, delete=False)
            path = handle.name
            try:
                with handle:
                    handle.write(data)
                source = directory.get_radio_by_image(path)
                low, high = source.get_features().memory_bounds
                memories = [
                    copy.deepcopy(memory)
                    for number in range(low, high + 1)
                    if not (memory := source.get_memory(number)).empty
                ]
                return memories
            finally:
                Path(path).unlink(missing_ok=True)

    def _import_memories(self, source_memories, placement='empty',
                         destination_start=None):
        """Validate and copy memories transactionally using one placement."""
        self._ensure_idle()
        radio = self._require_radio()

        low, high = radio.get_features().memory_bounds
        if placement not in {'empty', 'matching', 'append', 'range'}:
            raise WebServiceError('Unknown import placement policy.', 422)
        if placement == 'range' and (
                type(destination_start) is not int or
                not low <= destination_start <= high):
            raise WebServiceError(
                    f'Destination must be between {low} and {high}.', 422)
        if placement != 'range' and destination_start is not None:
            raise WebServiceError(
                    'A destination channel is valid only for range import.',
                    422)
        empty_slots = [
            number for number in range(low, high + 1)
            if radio.get_memory(number).empty
        ]
        if radio.get_features().has_infinite_number and placement == 'empty':
            empty_slots.extend(
                    range(high + 1, high + len(source_memories) + 1))
        if placement == 'empty':
            destinations = empty_slots
        elif placement == 'matching':
            destinations = [memory.number for memory in source_memories]
            if (any(type(number) is not int or not low <= number <= high
                    for number in destinations) or
                    len(destinations) != len(set(destinations))):
                raise WebServiceError(
                        'Matching import requires unique source channel '
                        'numbers within the destination range.', 422)
        else:
            if placement == 'append':
                used = [
                    number for number in range(low, high + 1)
                    if not radio.get_memory(number).empty
                ]
                destination_start = (max(used) + 1) if used else low
            destinations = list(
                    range(destination_start,
                          destination_start + len(source_memories)))
            if (destinations and destinations[-1] > high and
                    not radio.get_features().has_infinite_number):
                raise WebServiceError(
                        'The destination range exceeds this radio’s channel '
                        'bounds.', 409)
        if len(destinations) < len(source_memories):
            raise WebServiceError(
                    'The open image does not have enough empty memory '
                    'slots for the selected repeaters.', 409)
        prepared: list[
            tuple[
                int,
                chirp_common.Memory,
                list[chirp_common.ValidationWarning],
            ]
        ] = []
        rejected: list[RejectedSourceResult] = []
        for index, (source_memory, destination) in enumerate(
                zip(source_memories, destinations)):
            memory = copy.deepcopy(source_memory)
            memory.number = destination
            memory.empty = False
            warnings, errors = chirp_common.split_validation_msgs(
                    radio.validate_memory(memory))
            if errors:
                rejected.append({
                    'index': index,
                    'reason': '; '.join(str(error) for error in errors),
                })
                continue
            prepared.append((index, memory, warnings))

        if not prepared:
            if not empty_slots:
                raise WebServiceError(
                        'The open image has no empty memory slots.', 409)
            detail = '; '.join(item['reason'] for item in rejected)
            raise WebServiceError(
                    detail or 'No selected repeaters can be imported.',
                    422)
        backups = {
            memory.number: (
                copy.deepcopy(radio.get_memory(memory.number))
                if memory.number <= high else
                chirp_common.Memory(memory.number, empty=True))
            for _, memory, _ in prepared
        }
        written = []
        try:
            for _, memory, _ in prepared:
                written.append(memory.number)
                radio.set_memory(memory)
        except Exception as exc:
            for number in written:
                try:
                    if number in backups:
                        radio.set_memory(backups[number])
                    else:
                        radio.erase_memory(number)
                except Exception:
                    LOG.exception(
                            'Failed to restore memory %i after import',
                            number)
            raise WebServiceError(
                    'The radio driver could not import the selected '
                    'repeaters.', 422) from exc

        self.dirty = True
        self._record_memory_change(
                backups,
                {memory.number: copy.deepcopy(
                    radio.get_memory(memory.number))
                 for _, memory, _ in prepared})
        warnings = [
            str(warning)
            for _, _, item_warnings in prepared
            for warning in item_warnings
        ]
        return {
            'imported': len(prepared),
            'start': prepared[0][1].number,
            'rejected': rejected,
            'warnings': warnings,
        }

    def scoped_memories(self, scope, numbers=None, filters=None, match='all',
                        search='', sort='number', direction='asc',
                        hide_empty=False):
        """Return programmed memories for an explicit print/export scope."""
        with self.lock:
            self._ensure_idle()
            radio = self._require_radio()
            low, high = radio.get_features().memory_bounds
            if scope == 'all':
                ids = range(low, high + 1)
            elif scope == 'selected':
                if not numbers or len(numbers) > 1000:
                    raise WebServiceError(
                            'Select between 1 and 1,000 channels.', 422)
                if len(numbers) != len(set(numbers)):
                    raise WebServiceError(
                            'A channel can only be selected once.', 422)
                for number in numbers:
                    self._validate_memory_id(radio, number)
                ids = numbers
            elif scope == 'filtered':
                result = self.memories(
                        0, 1, search=search, sort=sort, direction=direction,
                        hide_empty=hide_empty, filters=filters or [],
                        match=match)
                result = self.memories(
                        0, result['total'], search=search, sort=sort,
                        direction=direction, hide_empty=hide_empty,
                        filters=filters or [], match=match)
                ids = [row['number'] for row in result['memories']]
            else:
                raise WebServiceError('Unknown print or export scope.', 422)
            return [
                copy.deepcopy(radio.get_memory(number))
                for number in ids if not radio.get_memory(number).empty
            ]

    def export_csv(self, scope='all', numbers=None, filters=None,
                   match='all', search='', sort='number', direction='asc',
                   hide_empty=False):
        """Return selected programmed memories in standard CHIRP CSV format."""
        with self.lock:
            memories = self.scoped_memories(
                    scope, numbers, filters, match, search, sort, direction,
                    hide_empty)
            output = io.StringIO(newline='')
            writer = csv.writer(output)
            writer.writerow(chirp_common.Memory.CSV_FORMAT)
            for memory in memories:
                writer.writerow(memory.to_csv())
            return output.getvalue()

    def print_rows(self, scope, numbers=None, filters=None, match='all',
                   search='', sort='number', direction='asc',
                   hide_empty=False):
        """Serialize the requested print scope without exposing radio state."""
        memories = self.scoped_memories(
                scope, numbers, filters, match, search, sort, direction,
                hide_empty)
        return {'memories': [self._memory_dict(memory) for memory in memories]}

    @staticmethod
    def _extra_value_node(value, path, label, owner):
        if isinstance(value, settings.RadioSettingValueBoolean):
            kind, current = 'boolean', bool(value.get_value())
        elif isinstance(value, settings.RadioSettingValueInteger):
            kind, current = 'integer', int(value.get_value())
        elif isinstance(value, settings.RadioSettingValueFloat):
            kind, current = 'float', float(value.get_value())
        elif isinstance(value, settings.RadioSettingValueList):
            kind, current = 'list', value.get_value()
        elif isinstance(value, settings.RadioSettingValueString):
            kind, current = 'string', str(value.get_value()).rstrip()
        else:
            return None
        node = {
            'type': kind,
            'label': label,
            'path': list(path),
            'value': current,
            'mutable': value.get_mutable(),
        }
        if kind == 'list':
            node['options'] = list(value.get_options())
        if kind in ('integer', 'float'):
            node['min'] = value.get_min()
            node['max'] = value.get_max()
            if kind == 'integer':
                node['step'] = value.get_step()
        if kind == 'string':
            node['max'] = value.maxlength
        warning = owner.get_warning(current)
        if warning:
            node['warning'] = warning
        return node

    @staticmethod
    def _extra_tree(group, prefix=()):
        """Serialize editable driver-specific memory settings."""
        nodes = []
        if not isinstance(group, settings.RadioSettingGroup):
            return nodes
        for element in group:
            if isinstance(element, settings.RadioSetting):
                path = (*prefix, element.get_name())
                value = element.value
                if isinstance(value, list):
                    children = [
                        node for index, item in enumerate(value)
                        if (node := DriverSession._extra_value_node(
                            item, (*path, index),
                            f'{element.get_shortname()} {index + 1}',
                            element))
                    ]
                    if children:
                        nodes.append({
                            'type': 'group',
                            'label': element.get_shortname(),
                            'children': children,
                        })
                else:
                    node = DriverSession._extra_value_node(
                            value, path, element.get_shortname(), element)
                    if node:
                        nodes.append(node)
                continue
            path = (*prefix, element.get_name())
            if isinstance(element, settings.RadioSettingGroup):
                children = DriverSession._extra_tree(element, path)
                if children:
                    nodes.append({
                        'type': 'group',
                        'label': element.get_shortname(),
                        'children': children,
                    })
                continue
        return nodes

    @staticmethod
    def _power_watts(power):
        return 10 ** ((float(power) - 30) / 10)

    @staticmethod
    def _memory_dict(memory):
        result = {field: getattr(memory, field, None)
                  for field in MEMORY_FIELDS}
        result.update({
            'number': DriverSession._memory_id(memory),
            'empty': memory.empty,
            'immutable': list(memory.immutable),
            'power': DriverSession._power_watts(memory.power)
            if memory.power is not None else None,
            'power_label': str(memory.power)
            if memory.power is not None else '',
            'extra': DriverSession._extra_tree(
                getattr(memory, 'extra', None),
                (memory.extra.get_name(),)
                if isinstance(memory.extra, settings.RadioSettingGroup)
                else ()),
        })
        return result

    def save_image(self, mark_clean=True):
        """Serialize the current image for the browser to download."""
        with self.lock:
            self._ensure_idle()
            radio = self._tab.radio
            if radio is None:
                raise WebServiceError(
                        'Open a radio image before editing.', 409)
            if isinstance(radio, chirp_common.LiveRadio):
                raise WebServiceError(
                        'Live radios do not have an image to save. Export '
                        'CSV to keep a channel-list copy.', 409)
            suffix = Path(self.source_name).suffix or '.img'
            handle = tempfile.NamedTemporaryFile(
                    prefix='chirp-web-save-', suffix=suffix, delete=False)
            path = handle.name
            handle.close()
            try:
                if isinstance(radio, chirp_common.CloneModeRadio):
                    radio.save_mmap(path)
                else:
                    radio.save(path)
                data = Path(path).read_bytes()
            finally:
                Path(path).unlink(missing_ok=True)
            if not data:
                raise WebServiceError(
                        'The radio driver did not save an image.', 500)
            if mark_clean:
                self.dirty = False
            return {
                'filename': self.source_name,
                'data_base64': base64.b64encode(data).decode('ascii'),
            }

    def close(self):
        """Release every open image and live-radio connection."""
        with self.lock:
            self._ensure_idle()
            for tab in self.tabs.values():
                self._release_tab(tab)
            self.tabs.clear()
            self.active_tab_id = None


def __getattr__(name):
    """Preserve deferred compatibility exports after service extraction."""
    if name in {'TransferManager', 'serial'}:
        from chirp_web.webui import transfers
        return getattr(transfers, name)
    raise AttributeError(name)
