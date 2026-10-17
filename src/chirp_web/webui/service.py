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
import logging
import re
import tempfile
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import TypedDict

from chirp_web import chirp_common, directory, settings

import serial
from serial.tools import list_ports

LOG = logging.getLogger(__name__)
MAX_IMAGE_SIZE = 20 * 1024 * 1024
MEMORY_FIELDS = (
        'name', 'freq', 'mode', 'duplex', 'offset', 'tmode', 'rtone',
        'ctone', 'dtcs', 'rx_dtcs', 'dtcs_polarity', 'cross_mode',
        'tuning_step', 'skip', 'comment',
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


class DriverSession:
    """Own the one local radio/image being edited by this app process."""

    def __init__(self):
        """Initialize the single in-process radio session."""
        self.lock = threading.RLock()
        self.radio = None
        self.source_name = ''
        self.temp_path = None
        self.dirty = False
        self.active_job = None
        self.source_results = {}

    def _require_radio(self):
        if self.radio is None:
            raise WebServiceError('Open a radio image before editing.', 409)
        return self.radio

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
            if self.dirty and not confirm_replace:
                raise WebServiceError(
                        'Confirm that you want to discard unsaved changes.',
                        409)
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
            self._replace_radio(radio, safe_name, new_path)
        return self.describe()

    def _replace_radio(self, radio, filename, temp_path):
        old_path = self.temp_path
        self.radio = radio
        self.source_name = filename
        self.temp_path = temp_path
        self.dirty = False
        if old_path and old_path != temp_path:
            Path(old_path).unlink(missing_ok=True)

    def _ensure_idle(self):
        if self.active_job:
            raise WebServiceError(
                    'Wait for the active radio transfer to finish.', 409)

    def describe(self):
        """Return the open radio's identity and supported memory features."""
        with self.lock:
            radio = self._require_radio()
            rf = radio.get_features()
            return {
                'name': radio.get_name(),
                'filename': self.source_name,
                'dirty': self.dirty,
                'supports_upload': isinstance(
                        radio, chirp_common.CloneModeRadio),
                'has_settings': rf.has_settings,
                'memory_bounds': list(rf.memory_bounds),
                'valid_special_chans': list(rf.valid_special_chans),
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

    def memories(self, start: int, limit: int):
        """Read a bounded range of memories from the open image."""
        with self.lock:
            self._ensure_idle()
            radio = self._require_radio()
            low, high = radio.get_features().memory_bounds
            start = max(low, start)
            end = min(high + 1, start + limit)
            rows = []
            for number in range(start, end):
                memory = radio.get_memory(number)
                row = {
                    field: getattr(memory, field, None)
                    for field in MEMORY_FIELDS
                }
                row.update({
                    'number': memory.number,
                    'empty': memory.empty,
                    'immutable': list(memory.immutable),
                    'power': str(memory.power)
                    if memory.power is not None else '',
                })
                rows.append(row)
            return {'start': start, 'end': end, 'total': high - low + 1,
                    'memories': rows}

    def update_memory(self, number: int, values: dict):
        """Validate and apply changes to a memory in the open image."""
        with self.lock:
            self._ensure_idle()
            radio = self._require_radio()
            rf = radio.get_features()
            low, high = rf.memory_bounds
            if not low <= number <= high:
                raise WebServiceError(
                        f'Memory number must be between {low} and {high}.',
                        422)
            if not values:
                raise WebServiceError('Provide at least one memory field.')
            memory = radio.get_memory(number)
            for field, value in values.items():
                if field not in MEMORY_FIELDS:
                    raise WebServiceError(f'Unsupported memory field: {field}',
                                          422)
                required_feature = {
                    'name': 'has_name',
                    'mode': 'has_mode',
                    'offset': 'has_offset',
                    'ctone': 'has_ctone',
                    'dtcs': 'has_dtcs',
                    'rx_dtcs': 'has_rx_dtcs',
                    'dtcs_polarity': 'has_dtcs_polarity',
                    'cross_mode': 'has_cross',
                    'tuning_step': 'has_tuning_step',
                    'comment': 'has_comment',
                }.get(field)
                if required_feature and not getattr(rf, required_feature):
                    raise WebServiceError(
                            f'The radio does not support {field}.', 422)
                if field in memory.immutable:
                    raise WebServiceError(
                            f'{field} cannot be changed for memory {number}.',
                            422)
                allowed = {
                    'mode': rf.valid_modes,
                    'duplex': rf.valid_duplexes,
                    'tmode': rf.valid_tmodes,
                    'rtone': rf.valid_tones,
                    'ctone': rf.valid_tones,
                    'dtcs': rf.valid_dtcs_codes,
                    'rx_dtcs': rf.valid_dtcs_codes,
                    'dtcs_polarity': rf.valid_dtcs_pols,
                    'cross_mode': rf.valid_cross_modes,
                    'tuning_step': rf.valid_tuning_steps,
                    'skip': rf.valid_skips,
                }.get(field)
                if allowed is not None and value not in allowed:
                    raise WebServiceError(
                            f'{value!r} is not supported for {field}.', 422)
                if field == 'name' and (
                        not isinstance(value, str) or
                        len(value) > rf.valid_name_length):
                    raise WebServiceError(
                            f'Name must be at most {rf.valid_name_length} '
                            'characters.', 422)
                if field in ('freq', 'offset') and (
                        isinstance(value, bool) or
                        not isinstance(value, (int, float)) or value < 0):
                    raise WebServiceError(
                            f'{field} must be a non-negative number.', 422)
                setattr(memory, field, value)

            warnings, errors = chirp_common.split_validation_msgs(
                    rf.validate_memory(memory))
            if errors:
                raise WebServiceError(
                        '; '.join(str(error) for error in errors), 422)
            radio.set_memory(memory)
            self.dirty = True
            return {'memory': self._memory_dict(radio.get_memory(number)),
                    'warnings': [str(warning) for warning in warnings]}

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
            self._ensure_idle()
            radio = self._require_radio()
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

            low, high = radio.get_features().memory_bounds
            empty_slots = [
                number for number in range(low, high + 1)
                if radio.get_memory(number).empty
            ]
            prepared: list[
                tuple[
                    int,
                    chirp_common.Memory,
                    list[chirp_common.ValidationWarning],
                ]
            ] = []
            rejected: list[RejectedSourceResult] = []
            for index in selected:
                memory = copy.deepcopy(source_memories[index])
                if len(prepared) >= len(empty_slots):
                    break
                memory.number = empty_slots[len(prepared)]
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
            if len(prepared) < len(selected) - len(rejected):
                raise WebServiceError(
                        'The open image does not have enough empty memory '
                        'slots for the selected repeaters.', 409)

            backups = {
                memory.number: copy.deepcopy(radio.get_memory(memory.number))
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
                        radio.set_memory(backups[number])
                    except Exception:
                        LOG.exception(
                                'Failed to restore memory %i after import',
                                number)
                raise WebServiceError(
                        'The radio driver could not import the selected '
                        'repeaters.', 422) from exc

            del self.source_results[token]
            self.dirty = True
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

    @staticmethod
    def _memory_dict(memory):
        result = {field: getattr(memory, field, None)
                  for field in MEMORY_FIELDS}
        result.update({
            'number': memory.number,
            'empty': memory.empty,
            'immutable': list(memory.immutable),
            'power': str(memory.power) if memory.power is not None else '',
        })
        return result

    def save_image(self):
        """Serialize the current image for the browser to download."""
        with self.lock:
            self._ensure_idle()
            radio = self._require_radio()
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
            self.dirty = False
            return {
                'filename': self.source_name,
                'data_base64': base64.b64encode(data).decode('ascii'),
            }

    def close(self):
        """Release the open image and its temporary backing file."""
        with self.lock:
            if self.temp_path:
                Path(self.temp_path).unlink(missing_ok=True)
            self.temp_path = None
            self.radio = None
            self.source_name = ''
            self.dirty = False


class TransferManager:
    """Run blocking serial transfers off the web request thread."""

    def __init__(self, session: DriverSession):
        """Create a transfer queue for one active radio session."""
        self.session = session
        self.executor = ThreadPoolExecutor(
                max_workers=1, thread_name_prefix='chirp-web-radio')
        self.lock = threading.Lock()
        self.jobs: dict[str, dict[str, object]] = {}

    @staticmethod
    def radios():
        """Return clone-mode radios that support serial transfers."""
        directory.import_drivers()
        result = []
        for ident, radio_class in sorted(directory.DRV_TO_RADIO.items()):
            if not issubclass(radio_class, chirp_common.CloneModeRadio):
                continue
            result.append({
                'id': ident,
                'name': radio_class.get_name(),
                'baud_rate': radio_class.BAUD_RATE,
            })
        return result

    @staticmethod
    def ports():
        """Return serial ports currently detected on this computer."""
        return [{'port': item.device, 'description': item.description}
                for item in list_ports.comports()]

    def start(self, operation: str, radio_id: str, port: str,
              confirm: bool = False, confirm_replace: bool = False):
        """Validate and queue one upload or download operation."""
        with self.session.lock:
            self.session._ensure_idle()
            if (operation == 'download' and self.session.dirty and
                    not confirm_replace):
                raise WebServiceError(
                        'Confirm that you want to discard unsaved changes.',
                        409)
            if operation == 'upload':
                radio = self.session._require_radio()
                if not isinstance(radio, chirp_common.CloneModeRadio):
                    raise WebServiceError(
                            'Upload is available only for clone-mode images.',
                            409)
                if not confirm:
                    raise WebServiceError(
                            'Confirm that you want to write this image to the '
                            'radio.', 400)
                radio_class = radio.__class__
            else:
                try:
                    radio_class = directory.get_radio(radio_id)
                except Exception as exc:
                    raise WebServiceError('Unknown radio model.', 404) from exc
                if not issubclass(radio_class, chirp_common.CloneModeRadio):
                    raise WebServiceError(
                            'Radio model does not support clone transfers.',
                            422)

            valid_ports = {item['port'] for item in self.ports()}
            if port not in valid_ports:
                raise WebServiceError(
                        'Select a serial port detected on this computer.',
                        422)
            job_id = str(uuid.uuid4())
            job = {
                'id': job_id,
                'operation': operation,
                'state': 'running',
                'progress': 0,
                'message': 'Starting transfer',
                'error': None,
            }
            with self.lock:
                self.jobs[job_id] = job
            self.session.active_job = job_id
            self.executor.submit(self._run, job_id, radio_class, port,
                                 operation)
            return dict(job)

    def _set_progress(self, job_id: str, status):
        with self.lock:
            job = self.jobs[job_id]
            maximum = status.max or 1
            job['progress'] = max(0, min(100, int(status.cur * 100 / maximum)))
            job['message'] = str(status.msg)

    def _run(self, job_id: str, radio_class, port: str, operation: str):
        pipe = None
        temp_path = None
        failure = None
        try:
            pipe = serial.Serial(port=port, timeout=0.5)
            if operation == 'download':
                radio = radio_class(pipe)
            else:
                with self.session.lock:
                    radio = self.session._require_radio()
                    radio.set_pipe(pipe)
            radio.status_fn = lambda status: self._set_progress(
                    job_id, status)
            if operation == 'download':
                radio.sync_in()
                handle = tempfile.NamedTemporaryFile(
                        prefix='chirp-web-download-',
                        suffix='.img',
                        delete=False)
                temp_path = handle.name
                handle.close()
                radio.save_mmap(temp_path)
                with self.session.lock:
                    self.session._replace_radio(
                            radio, f'{radio_class.get_name()}.img', temp_path)
                temp_path = None
            else:
                radio.sync_out()
                with self.session.lock:
                    self.session.dirty = False
        except Exception as exc:
            failure = exc
            LOG.exception('Radio %s failed', operation)
        finally:
            try:
                if pipe is not None and pipe.is_open:
                    pipe.close()
            except Exception as exc:
                LOG.exception(
                        'Unable to close serial port after %s', operation)
                if failure is None:
                    failure = exc
            if temp_path:
                Path(temp_path).unlink(missing_ok=True)
            with self.session.lock:
                if self.session.active_job == job_id:
                    self.session.active_job = None
                with self.lock:
                    if failure is None:
                        self.jobs[job_id].update(
                                state='complete', progress=100,
                                message='Transfer done')
                    else:
                        self.jobs[job_id].update(
                                state='failed', error=str(failure),
                                message='Transfer failed')

    def get(self, job_id: str):
        """Return progress for one transfer job."""
        with self.lock:
            job = self.jobs.get(job_id)
            if job is None:
                raise WebServiceError('Transfer job was not found.', 404)
            return dict(job)

    def close(self):
        """Stop accepting transfers and release session resources."""
        self.executor.shutdown(wait=False, cancel_futures=True)
        self.session.close()
