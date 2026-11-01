"""Undo and redo snapshots for one web radio session."""


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


class MemoryHistory:
    """Record and replay bounded radio-memory changes."""

    def __init__(self, session, error_type, log):
        self.session = session
        self.error_type = error_type
        self.log = log

    def record(self, before, after):
        """Store one reversible memory change and clear redo history."""
        if not before:
            return
        self.session.undo_stack.append({
            number: (copy.deepcopy(before[number]),
                     copy.deepcopy(after[number]))
            for number in before
        })
        del self.session.undo_stack[:-50]
        self.session.redo_stack.clear()

    def summary(self):
        """Return whether a change is available in either direction."""
        return {
            'can_undo': bool(self.session.undo_stack),
            'can_redo': bool(self.session.redo_stack),
        }

    def undo(self):
        """Replay the newest change in reverse."""
        self._apply(self.session.undo_stack, self.session.redo_stack)
        return self.summary()

    def redo(self):
        """Replay the newest undone change."""
        self._apply(self.session.redo_stack, self.session.undo_stack)
        return self.summary()

    def _apply(self, source, target):
        with self.session.lock:
            self.session._ensure_idle()
            radio = self.session._require_radio()
            if not source:
                raise self.error_type('There is no change to replay.', 409)
            change = source[-1]
            current = {
                number: copy.deepcopy(radio.get_memory(number))
                for number in change
            }
            try:
                for number, (before, after) in change.items():
                    memory = (
                            before if target is self.session.redo_stack
                            else after)
                    if memory.empty:
                        radio.erase_memory(number)
                    else:
                        radio.set_memory(copy.deepcopy(memory))
            except Exception as exc:
                for number, memory in current.items():
                    try:
                        if memory.empty:
                            radio.erase_memory(number)
                        else:
                            radio.set_memory(memory)
                    except Exception:
                        self.log.exception(
                                'Failed to restore memory %s after history '
                                'operation', number)
                raise self.error_type(
                        'The radio driver could not replay this change.',
                        422) from exc
            source.pop()
            target.append(change)
            self.session.dirty = True
