"""Memory mutation workflows for one browser radio session."""


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


import copy
import logging
import math
import uuid

from chirp_web import chirp_common, settings


LOG = logging.getLogger(__name__)
MEMORY_FIELDS = (
        'name', 'freq', 'mode', 'duplex', 'offset', 'tmode', 'rtone',
        'ctone', 'dtcs', 'rx_dtcs', 'dtcs_polarity', 'cross_mode',
        'tuning_step', 'skip', 'comment', 'power',
)


class MemoryOperations:
    """Apply editable memory operations through a DriverSession."""

    def __init__(self, session, error_type):
        object.__setattr__(self, 'session', session)
        object.__setattr__(self, 'error_type', error_type)

    def __getattr__(self, name):
        return getattr(self.session, name)

    def __setattr__(self, name, value):
        if name in {'dirty', 'undo_stack', 'redo_stack'}:
            setattr(self.session, name, value)
        else:
            object.__setattr__(self, name, value)

    def delete_memories(self, numbers: list[int | str], shift=''):
        """Erase selected channels, rolling back on driver failures."""
        with self.lock:
            self._ensure_idle()
            radio = self._require_radio()
            rf = radio.get_features()
            if not rf.can_delete:
                raise self.error_type(
                        'This radio does not support deleting memories.', 422)
            if not numbers:
                raise self.error_type('Select at least one memory.', 422)
            if len(numbers) != len(set(numbers)):
                raise self.error_type(
                        'A memory can only be selected once.', 422)
            for number in numbers:
                self._validate_memory_id(radio, number)
            if shift not in ('', 'block', 'all'):
                raise self.error_type('Invalid channel shift mode.', 422)
            if shift and any(
                    not isinstance(number, int) for number in numbers):
                raise self.error_type(
                        'Special channels cannot be shifted.', 422)
            deleted = sorted(number for number in numbers
                             if isinstance(number, int))
            if shift:
                low, high = rf.memory_bounds
                end = high
                if shift == 'block':
                    for number in range(max(deleted) + 1, high + 1):
                        if radio.get_memory(number).empty:
                            end = number - 1
                            break
                affected: range | list[int | str] = range(
                        min(deleted), end + 1)
            else:
                affected = numbers
            backups: dict[int | str, chirp_common.Memory] = {
                number: copy.deepcopy(radio.get_memory(number))
                for number in affected
            }
            after: dict[int | str, chirp_common.Memory] = copy.deepcopy(
                    backups)
            if shift:
                slots = list(affected)
                remaining = [
                    copy.deepcopy(backups[number])
                    for number in slots if number not in deleted
                ]
                remaining.extend(
                    self._empty_memory(number)
                    for number in slots[len(remaining):])
                after = {
                    number: memory
                    for number, memory in zip(slots, remaining)
                }
            else:
                for number in numbers:
                    after[number] = self._empty_memory(number)
            erased = sum(
                not radio.get_memory(number).empty for number in numbers)
            attempted = []
            try:
                for number in sorted(after):
                    memory = after[number]
                    attempted.append(number)
                    if memory.empty:
                        radio.erase_memory(number)
                    else:
                        radio.set_memory(memory)
            except Exception as exc:
                for number in reversed(attempted):
                    try:
                        memory = backups[number]
                        if memory.empty:
                            radio.erase_memory(number)
                        else:
                            radio.set_memory(memory)
                    except Exception:
                        LOG.exception(
                                'Failed to restore memory %s after deletion',
                                number)
                raise self.error_type(
                        'The radio driver could not delete the selected '
                        'memories.', 422) from exc
            if erased or shift:
                self._record_memory_change(
                        backups, {
                            number: copy.deepcopy(radio.get_memory(number))
                            for number in backups
                        })
                self.dirty = True
            return {'deleted': erased}

    def move_memories(self, numbers: list[int], direction: str):
        """Move selected channels one position while preserving their order."""
        with self.lock:
            self._ensure_idle()
            radio = self._require_radio()
            features = radio.get_features()
            if not features.can_delete:
                raise self.error_type(
                        'This radio does not support channel rearrangement.',
                        422)
            low, high = features.memory_bounds
            if direction not in ('up', 'down') or not numbers:
                raise self.error_type('Select channels and a direction.', 422)
            if any(type(number) is not int or not low <= number <= high
                   for number in numbers):
                raise self.error_type(
                        'Only numbered channels can be moved.', 422)
            selected = set(numbers)
            ordered = sorted(selected)
            groups: list[list[int]] = []
            for number in ordered:
                if not groups or number > groups[-1][-1] + 1:
                    groups.append([number])
                else:
                    groups[-1].append(number)
            ranges = []
            for group in groups:
                first, last = group[0], group[-1]
                if direction == 'up' and first > low:
                    ranges.append((first - 1, last, -1))
                elif direction == 'down' and last < high:
                    ranges.append((first, last + 1, 1))
            if not ranges:
                return {'moved': 0}
            affected = {
                number for start, end, _ in ranges
                for number in range(start, end + 1)
            }
            before = {
                number: copy.deepcopy(radio.get_memory(number))
                for number in affected
            }
            after = copy.deepcopy(before)
            for start, end, delta in ranges:
                span = [copy.deepcopy(before[number])
                        for number in range(start, end + 1)]
                if delta < 0:
                    reordered = span[1:] + span[:1]
                else:
                    reordered = span[-1:] + span[:-1]
                for number, memory in zip(range(start, end + 1), reordered):
                    memory.number = number
                    after[number] = memory
            try:
                for number in sorted(after):
                    memory = after[number]
                    if memory.empty:
                        radio.erase_memory(number)
                    else:
                        radio.set_memory(memory)
            except Exception as exc:
                self._restore_memories(radio, before, after)
                raise self.error_type(
                        'The radio driver could not move these channels.',
                        422) from exc
            self._record_memory_change(
                    before, {number: copy.deepcopy(radio.get_memory(number))
                             for number in affected})
            self.dirty = True
            return {'moved': len(selected)}

    def insert_memory_row(self, number: int):
        """Open an empty numbered channel by shifting later channels down."""
        with self.lock:
            self._ensure_idle()
            radio = self._require_radio()
            features = radio.get_features()
            if not features.can_delete:
                raise self.error_type(
                        'This radio does not support channel insertion.',
                        422)
            low, high = features.memory_bounds
            if type(number) is not int or not low <= number < high:
                raise self.error_type('Insert position is out of range.', 422)
            empty = next((candidate for candidate in range(number, high + 1)
                          if radio.get_memory(candidate).empty), None)
            if empty is None:
                raise self.error_type(
                        'There is no empty channel available for insertion.',
                        409)
            before = {
                channel: copy.deepcopy(radio.get_memory(channel))
                for channel in range(number, empty + 1)
            }
            after = {}
            for channel in range(number + 1, empty + 1):
                memory = copy.deepcopy(before[channel - 1])
                memory.number = channel
                after[channel] = memory
            after[number] = self._empty_memory(number)
            try:
                for channel in range(number, empty + 1):
                    memory = after[channel]
                    if memory.empty:
                        radio.erase_memory(channel)
                    else:
                        radio.set_memory(memory)
            except Exception as exc:
                self._restore_memories(radio, before, after)
                raise self.error_type(
                        'The radio driver could not insert a channel row.',
                        422) from exc
            self._record_memory_change(
                    before, {channel: copy.deepcopy(radio.get_memory(channel))
                             for channel in before})
            self.dirty = True
            return {'inserted': number}

    @staticmethod
    def _restore_memories(radio, before, attempted):
        for number in reversed(list(attempted)):
            memory = before[number]
            try:
                if memory.empty:
                    radio.erase_memory(number)
                else:
                    radio.set_memory(copy.deepcopy(memory))
            except Exception:
                LOG.exception('Failed to restore memory %s', number)

    def copy_memories(self, numbers: list[int | str], cut=False):
        """Copy selected channels to a server-side portable clipboard."""
        with self.lock:
            self._ensure_idle()
            radio = self._require_radio()
            if not numbers or len(numbers) > 200:
                raise self.error_type(
                        'Select between 1 and 200 channels.', 422)
            memories: list[chirp_common.Memory] = []
            for number in numbers:
                self._validate_memory_id(radio, number)
                memory = copy.deepcopy(radio.get_memory(number))
                if memory.empty:
                    continue
                memory.number = len(memories)
                memory.extd_number = ''
                memory.extra = settings.RadioSettingGroup('extra', 'Extra')
                memories.append(memory)
            if not memories:
                raise self.error_type('The selection contains no channels.',
                                      422)
            token = str(uuid.uuid4())
            self.clipboard_results[token] = memories
            if len(self.clipboard_results) > 10:
                self.clipboard_results.pop(next(iter(self.clipboard_results)))
            if cut:
                self.delete_memories(numbers)
            return {'clipboard_id': token, 'count': len(memories)}

    def paste_memories(self, token: str, start: int, overwrite=False):
        """Paste clipboard channels at explicit destinations."""
        with self.lock:
            self._ensure_idle()
            radio = self._require_radio()
            memories = self.clipboard_results.get(token)
            if memories is None:
                raise self.error_type('The clipboard has expired.', 404)
            low, high = radio.get_features().memory_bounds
            destinations = range(start, start + len(memories))
            if (type(start) is not int or start < low or
                    start + len(memories) - 1 > high):
                raise self.error_type('Paste range is outside channel bounds.',
                                      422)
            before = {
                number: copy.deepcopy(radio.get_memory(number))
                for number in destinations
            }
            if not overwrite and any(not memory.empty
                                     for memory in before.values()):
                raise self.error_type(
                        'Paste would overwrite channels. Confirm overwrite.',
                        409)
            after = {}
            warnings: list[str] = []
            for destination, source in zip(destinations, memories):
                memory = copy.deepcopy(source)
                memory.number = destination
                try:
                    warnings_found, errors = (
                        chirp_common.split_validation_msgs(
                            radio.validate_memory(memory)))
                except Exception as exc:
                    raise self.error_type(
                            f'Channel {destination}: {exc}', 422) from exc
                if errors:
                    raise self.error_type(
                            f'Channel {destination}: ' +
                            '; '.join(str(error) for error in errors), 422)
                warnings.extend(str(warning) for warning in warnings_found)
                after[destination] = memory
            try:
                for number, memory in after.items():
                    radio.set_memory(memory)
            except Exception as exc:
                self._restore_memories(radio, before, after)
                raise self.error_type(
                        'The radio driver could not paste the channels.',
                        422) from exc
            self._record_memory_change(
                    before, {number: copy.deepcopy(radio.get_memory(number))
                             for number in before})
            self.dirty = True
            return {'pasted': len(after), 'warnings': warnings}

    def update_memory(self, number: int | str, values: dict,
                      extra_changes=None):
        """Validate and apply changes to a memory in the open image."""
        with self.lock:
            self._ensure_idle()
            radio = self._require_radio()
            self._validate_memory_id(radio, number)
            rf = radio.get_features()
            if not values and not extra_changes:
                raise self.error_type('Provide at least one memory field.')
            memory = radio.get_memory(number)
            original = copy.deepcopy(memory)
            txfreq = values.pop('txfreq', None)
            if txfreq is not None:
                if ('offset' in memory.immutable or
                        'duplex' in memory.immutable):
                    raise self.error_type(
                            'Transmit frequency cannot be changed for this '
                            'channel.', 422)
                receive_frequency = values.get('freq', memory.freq)
                if 'split' in rf.valid_duplexes:
                    memory.duplex = 'split'
                    memory.offset = txfreq
                else:
                    memory.duplex = (
                        '' if txfreq == receive_frequency else
                        '-' if txfreq < receive_frequency else '+')
                    memory.offset = abs(txfreq - receive_frequency)
            for field_name, value in values.items():
                if field_name not in MEMORY_FIELDS:
                    raise self.error_type(
                            f'Unsupported memory field: {field_name}',
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
                }.get(field_name)
                if field_name == 'power' and not (
                        rf.has_variable_power or rf.valid_power_levels):
                    raise self.error_type(
                            'The radio does not support power selection.',
                            422)
                if required_feature and not getattr(rf, required_feature):
                    raise self.error_type(
                            f'The radio does not support {field_name}.', 422)
                if field_name in memory.immutable:
                    raise self.error_type(
                            f'{field_name} cannot be changed for memory '
                            f'{number}.',
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
                }.get(field_name)
                if allowed is not None and value not in allowed:
                    raise self.error_type(
                            f'{value!r} is not supported for {field_name}.',
                            422)
                if field_name == 'name' and (
                        not isinstance(value, str) or
                        len(value) > rf.valid_name_length):
                    raise self.error_type(
                            f'Name must be at most {rf.valid_name_length} '
                            'characters.', 422)
                if field_name in ('freq', 'offset') and (
                        isinstance(value, bool) or
                        not isinstance(value, (int, float)) or value < 0):
                    raise self.error_type(
                            f'{field_name} must be a non-negative number.',
                            422)
                if field_name == 'power':
                    if rf.has_variable_power:
                        memory.power = chirp_common.parse_power(str(value))
                    else:
                        level = next((
                            item for item in rf.valid_power_levels
                            if math.isclose(
                                self._power_watts(item), float(value),
                                rel_tol=1e-6)
                        ), None)
                        if level is None:
                            raise self.error_type(
                                    'Power level is not supported.', 422)
                        memory.power = level
                else:
                    setattr(memory, field_name, value)

            seen_extra = set()
            for change in extra_changes or []:
                path = change['path']
                key = tuple(path)
                if key in seen_extra:
                    raise self.error_type(
                            'An extra field can only be changed once.',
                            422)
                seen_extra.add(key)
                value, owner = self._find_setting_value(
                        memory.extra, path)
                if not value.get_mutable():
                    raise self.error_type(
                            'The selected extra field is read-only.', 422)
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
                    valid_type = False
                if not valid_type:
                    raise self.error_type(
                            'The value type does not match this extra field.',
                            422)
                try:
                    value.set_value(requested)
                except (settings.InvalidValueError, ValueError,
                        TypeError) as exc:
                    raise self.error_type(str(exc), 422) from exc
                warning = owner.get_warning(value.get_value())
                if warning:
                    raise self.error_type(
                            str(warning) +
                            ' Driver-specific warning requires radio-level '
                            'confirmation and cannot be bypassed here.',
                            409)
            warnings, errors = chirp_common.split_validation_msgs(
                    rf.validate_memory(memory))
            if errors:
                raise self.error_type(
                        '; '.join(str(error) for error in errors), 422)
            radio.set_memory(memory)
            self._record_memory_change(
                    {number: original},
                    {number: copy.deepcopy(radio.get_memory(number))})
            self.dirty = True
            return {'memory': self._memory_dict(radio.get_memory(number)),
                    'warnings': [str(warning) for warning in warnings]}

    def bulk_update_memories(self, numbers, values, extra_changes=None):
        """Apply the same supported field changes to selected memories."""
        with self.lock:
            self._ensure_idle()
            radio = self._require_radio()
            if len(numbers) < 2 or len(numbers) > 200:
                raise self.error_type(
                        'Select between 2 and 200 channels to edit.', 422)
            if len(numbers) != len(set(numbers)):
                raise self.error_type(
                        'A channel can only be selected once.', 422)
            for number in numbers:
                self._validate_memory_id(radio, number)
                if radio.get_memory(number).empty:
                    raise self.error_type(
                            'Bulk editing requires programmed channels.',
                            422)

            before = {
                number: copy.deepcopy(radio.get_memory(number))
                for number in numbers
            }
            previous_undo = copy.deepcopy(self.undo_stack)
            previous_redo = copy.deepcopy(self.redo_stack)
            was_dirty = self.dirty
            warnings = []
            try:
                for number in numbers:
                    result = self.update_memory(
                            number, copy.deepcopy(values),
                            copy.deepcopy(extra_changes))
                    warnings.extend(
                            f'Channel {number}: {warning}'
                            for warning in result['warnings'])
            except Exception:
                self._restore_memories(radio, before, before)
                self.undo_stack = previous_undo
                self.redo_stack = previous_redo
                self.dirty = was_dirty
                raise
            self.undo_stack = previous_undo
            self.redo_stack = previous_redo
            self._record_memory_change(
                    before, {
                        number: copy.deepcopy(radio.get_memory(number))
                        for number in numbers
                    })
            return {'updated': len(numbers), 'warnings': warnings}

    def arrange_memories(self, numbers, operation, field='name',
                         direction='asc'):
        """Sort or cluster a contiguous run of numbered channels."""
        with self.lock:
            self._ensure_idle()
            radio = self._require_radio()
            if not radio.get_features().can_delete:
                raise self.error_type(
                        'This radio does not support channel arrangement.',
                        422)
            if operation not in ('sort', 'cluster'):
                raise self.error_type('Unknown arrangement operation.', 422)
            if operation == 'sort' and field not in {
                    'name', 'freq', 'mode', 'duplex', 'offset', 'tmode',
                    'comment', 'rtone'}:
                raise self.error_type('Unsupported sort field.', 422)
            if direction not in ('asc', 'desc'):
                raise self.error_type('Invalid sort direction.', 422)
            if len(numbers) < 2 or len(numbers) > 200:
                raise self.error_type(
                        'Select between 2 and 200 channels.', 422)
            if (any(type(number) is not int for number in numbers) or
                    len(numbers) != len(set(numbers))):
                raise self.error_type(
                        'Arrange only unique numbered channels.', 422)
            ordered = sorted(numbers)
            if ordered[-1] - ordered[0] + 1 != len(ordered):
                raise self.error_type(
                        'Selected channels must be contiguous.', 422)
            radio_memories = [
                radio.get_memory(number) for number in ordered
            ]
            if any(memory.extd_number for memory in radio_memories):
                raise self.error_type(
                        'Special channels cannot be arranged.', 422)
            before = {
                number: copy.deepcopy(memory)
                for number, memory in zip(ordered, radio_memories)
            }
            if operation == 'cluster':
                sorted_memories = sorted(
                    radio_memories,
                    key=lambda memory: memory.empty)
            else:
                numeric_fields = {'freq', 'offset', 'rtone'}
                sorted_memories = sorted(
                    radio_memories,
                    key=lambda memory: (
                        getattr(memory, field) is None,
                        (
                            float(getattr(memory, field) or 0)
                            if field in numeric_fields
                            else str(getattr(memory, field) or '').casefold()
                        ),
                    ),
                    reverse=direction == 'desc')
            after = {}
            for number, memory in zip(ordered, sorted_memories):
                updated = copy.deepcopy(memory)
                updated.number = number
                after[number] = updated
            try:
                for number, memory in after.items():
                    if memory.empty:
                        radio.erase_memory(number)
                    else:
                        radio.set_memory(memory)
            except Exception as exc:
                self._restore_memories(radio, before, after)
                raise self.error_type(
                        'The radio driver could not arrange the channels.',
                        422) from exc
            self._record_memory_change(
                    before, {
                        number: copy.deepcopy(radio.get_memory(number))
                        for number in ordered
                    })
            self.dirty = True
            return {'arranged': len(ordered)}
