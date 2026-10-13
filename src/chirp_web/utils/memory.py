"""Classes relating to memory."""

# Copyright 2008 Tom Masterson <kd7cyu@gmail.com>
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

# import inspect
import logging
from typing import Any, Iterable, Protocol

from chirp_web.errors import (
        # ImmutableValueError,
        InvalidDataError,
        InvalidMemoryLocation,
)
from chirp_web.utils.common import (
        ALL_DTCS_CODES,
        CROSS_MODES,
        DTCS_CODES,
        MODES,
        SKIP_VALUES,
        TONES,
        TONE_MODES,
        VALIDTONE,
        format_freq,
        parse_freq,
)
from chirp_web.utils.powerlevel import PowerLevel


LOG = logging.getLogger(__name__)
SEPCHAR: str = ','


class _ExtraSetting(Protocol):
    """The setting interface used when dumping memory extras."""

    value: object

    def get_name(self) -> str: ...


class Memory:
    """Base class for a single radio memory."""

    freq: float = 0
    number: int = 0
    extd_number: str = ''
    name: str = ''
    vfo: int = 0
    rtone: float = 88.5
    ctone: float = 88.5
    dtcs: int = 23
    rx_dtcs: int = 23
    tmode: str = ''
    cross_mode: str = 'Tone->Tone'
    dtcs_polarity: str = 'NN'
    skip: str = ''
    power: PowerLevel | None = None
    duplex: str = ''
    offset: float = 600000
    mode: str = 'FM'
    tuning_step: float = 5.0
    comment: str = ''
    empty: bool = False
    immutable: list[str] = []
    dv_urcall: str = 'CQCQCQ'
    dv_rpt1call: str = ''
    dv_rpt2call: str = ''
    dv_code: int = 0
    dv_mem: bool = False

    # A RadioSettingGroup of additional settings supported by the radio,
    # or an empty list if none
    extra: Iterable[_ExtraSetting] = []

    def __init__(self, number: int = 0, empty: bool = False,
                 name: str = '', dv_mem: bool = False) -> None:
        """Construct a memory.

        Parameters:
           number:  Memory number.
           Empty:  Is this memory empty?
           name:  String label for memory
           dv_mem:  Tells if this is a dv memory.
        """
        self.freq = 0
        self.number = number
        self.extd_number = ''
        self.name = name
        self.vfo = 0
        self.rtone = 88.5
        self.ctone = 88.5
        self.dtcs = 23
        self.rx_dtcs = 23
        self.tmode = ''
        self.cross_mode = 'Tone->Tone'
        self.dtcs_polarity = 'NN'
        self.skip = ''
        self.power = None
        self.duplex = ''
        self.offset = 600000
        self.mode = 'FM'
        self.tuning_step = 5.0
        self.comment = ''
        self.empty = empty
        self.immutable = []
        self.dv_mem = dv_mem
        self.extra = []

    _valid_map: dict[str, Any] = {
        'rtone':          VALIDTONE,
        'ctone':          VALIDTONE,
        'dtcs':           frozenset(ALL_DTCS_CODES),
        'rx_dtcs':        frozenset(ALL_DTCS_CODES),
        'tmode':          frozenset(TONE_MODES),
        'dtcs_polarity':  frozenset(('NN', 'NR', 'RN', 'RR')),
        'cross_mode':     frozenset(CROSS_MODES),
        'mode':           frozenset(MODES),
        'duplex':         frozenset(('', '+', '-', 'split', 'off')),
        'skip':           frozenset(SKIP_VALUES),
        'empty':          frozenset((True, False)),
        'dv_code':        frozenset(range(100)),
    }

    def __repr__(self) -> str:
        """Return a debug representation of this memory."""
        ident, vals = self.debug_dump()
        details = ', '.join(f'{key}={value!r}' for key, value in vals)
        return f'<Memory {ident}: {details}>'

    def debug_diff(self, other: object, delim: str = '/') -> str:
        """Get debug info."""
        if not isinstance(other, Memory):
            return NotImplemented
        my_ident, my_dump = self.debug_dump()
        my_vals = dict(my_dump)
        om_ident, om_dump = other.debug_dump()
        om_vals = dict(om_dump)
        diffs = []
        if my_ident != om_ident:
            diffs.append(f'ident={my_ident}{delim}{om_ident}')
        for k in sorted(my_vals.keys() | om_vals.keys()):
            myval = my_vals.get(k, '<missing>')
            omval = om_vals.get(k, '<missing>')
            if myval != omval:
                diffs.append(f'{k}={myval!r}{delim}{omval!r}')
        return ','.join(diffs)

    def debug_dump(self) -> tuple[str, list[tuple[str, Any]]]:
        """Return the memory identifier and its debug values."""
        vals = [(k, v) for k, v in self.__dict__.items()
                if k not in ('extra', 'number', 'extd_number')]
        for extra in self.extra:
            vals.append((f'extra.{extra.get_name()}', str(extra.value)))
        if self.extd_number:
            ident = f'{self.extd_number}({self.number})'
        else:
            ident = str(self.number)
        return ident, vals

    def dupe(self) -> object:
        """Return a shallow copy of @self."""
        mem = self.__class__()
        mem.__dict__.update(self.__dict__)
        return mem

    def clone(self, source: object) -> None:
        """Absorb all of the properties of @source."""
        if not isinstance(source, Memory):
            return NotImplemented
        self.__dict__.update(source.__dict__)

    CSV_FORMAT = ['Location', 'Name', 'Frequency',
                  'Duplex', 'Offset', 'Tone',
                  'rToneFreq', 'cToneFreq', 'DtcsCode',
                  'DtcsPolarity', 'RxDtcsCode',
                  'CrossMode',
                  'Mode', 'TStep',
                  'Skip', 'Power', 'Comment',
                  'URCALL', 'RPT1CALL', 'RPT2CALL', 'DVCODE']

    # @classmethod
    def valid_setting(self, name: str, val: Any) -> bool:
        """Check to see if this is a valid setting."""
        if not hasattr(self, name):
            return False
        if name in self.immutable:
            return False
        if name in self._valid_map:
            valid = self._valid_map[name]
            if callable(valid):
                if not valid(val):
                    return False
            elif val not in valid:
                return False
        return True

    def __str__(self) -> str:
        """Create a string version of this memory."""
        if self.tmode == 'Tone':
            tenc = '*'
        else:
            tenc = ' '
        if self.tmode == 'TSQL':
            tsql = '*'
        else:
            tsql = ' '
        if self.tmode == 'DTCS':
            dtcs = '*'
        else:
            dtcs = ' '
        if self.duplex == '':
            dup = '/'
        else:
            dup = self.duplex
        if self.extd_number == '':
            tnum = str(self.number)
        else:
            tnum = str(self.extd_number)
        return (f'Memory {tnum}: '
                f'{format_freq(int(self.freq))}'
                f'{dup}{format_freq(int(self.offset))} '
                f'{self.mode} ({self.name}) r{self.rtone:.1f}{tenc} '
                f'c{self.ctone:.1f}{tsql} '
                f'd{self.dtcs:%03d}{dtcs}{self.dtcs_polarity} '
                f'[{self.tuning_step:.2f}]')

    def to_csv(self) -> list[str]:
        """Return a CSV representation of this memory."""
        return [
            f'{self.number}',
            f'{self.name}',
            format_freq(int(self.freq)),
            f'{self.duplex}',
            format_freq(int(self.offset)),
            f'{self.tmode}',
            f'{self.rtone:.1f}',
            f'{self.ctone:.1f}',
            f'{self.dtcs:03d}',
            f'{self.dtcs_polarity}',
            f'{self.rx_dtcs:03d}',
            f'{self.cross_mode}',
            f'{self.mode}',
            f'{self.tuning_step:.2f}',
            f'{self.skip}',
            f'{self.power}',
            f'{self.comment}',
            '', '', '', '']

    @classmethod
    def _from_csv(cls, _line: str) -> object:
        line = _line.strip()
        if line.startswith('Location'):
            raise InvalidMemoryLocation('Non-CSV line')

        vals = line.split(SEPCHAR)
        if len(vals) < 15:
            raise InvalidDataError('CSV format error ' +
                                   '(15 columns expected)')

        if vals[12] == 'DV':
            mem = cls(dv_mem=True)
        else:
            mem = cls()

        mem.really_from_csv(vals)
        return mem

    def really_from_csv(self, vals: Any) -> bool:
        """Careful parsing of split-out @vals."""
        if len(vals) < 15:
            raise InvalidDataError('CSV format error (15 columns expected)')

        try:
            self.number = int(vals[0])
        except (TypeError, ValueError):
            raise InvalidDataError(
                f'Location {vals[0]} is not a valid integer')

        self.name = vals[1]

        try:
            self.freq = parse_freq(vals[2])
        except (TypeError, ValueError):
            raise InvalidDataError('Frequency is not a valid number')

        if vals[3].strip() in ['+', '-', '']:
            self.duplex = vals[3].strip()
        else:
            raise InvalidDataError('Duplex is not +,-, or empty')

        try:
            self.offset = parse_freq(vals[4])
        except (TypeError, ValueError):
            raise InvalidDataError('Offset is not a valid number')

        self.tmode = vals[5]
        if self.tmode not in TONE_MODES:
            raise InvalidDataError(f'Invalid tone mode {self.tmode}')

        try:
            self.rtone = float(vals[6])
        except (TypeError, ValueError):
            raise InvalidDataError('rTone is not a valid number')
        if self.rtone not in TONES:
            raise InvalidDataError('rTone is not valid')

        try:
            self.ctone = float(vals[7])
        except (TypeError, ValueError):
            raise InvalidDataError('cTone is not a valid number')
        if self.ctone not in TONES:
            raise InvalidDataError('cTone is not valid')

        try:
            self.dtcs = int(vals[8], 10)
        except (TypeError, ValueError):
            raise InvalidDataError('DTCS code is not a valid number')
        if self.dtcs not in DTCS_CODES:
            raise InvalidDataError('DTCS code is not valid')

        try:
            self.rx_dtcs = int(vals[10], 10)
        except (TypeError, ValueError):
            raise InvalidDataError('DTCS Rx code is not a valid number')
        if self.rx_dtcs not in DTCS_CODES:
            raise InvalidDataError('DTCS Rx code is not valid')

        if vals[9] in ['NN', 'NR', 'RN', 'RR']:
            self.dtcs_polarity = vals[9]
        else:
            raise InvalidDataError('DtcsPolarity is not valid')

        self.cross_mode = vals[11]
        if vals[12] in MODES:
            self.mode = vals[12]
        else:
            raise InvalidDataError('Mode is not valid')

        try:
            self.tuning_step = float(vals[13])
        except (TypeError, ValueError):
            raise InvalidDataError('Tuning step is invalid')

        self.skip = vals[14]

        return True
