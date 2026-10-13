"""Radio classes."""

# Copyright 2025 Tom Masterson <kd7cyu@gmail.com>
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
import os
import sys

from chirp_web.errors import (
        ImmutableValueError,
)
from chirp_web.utils.common import (
        CHARSET_UPPER_NUMERIC,
        COMMON_TUNING_STEPS,
        CROSS_MODES,
        DTCS_CODES,
        MODES,
        TONES,
        VALIDTONE,
)
from chirp_web.utils.memory import Memory


def console_status(status):
    """Write a status object to the console when warning output is enabled."""
    from chirp_web import logger

    if not logger.is_visible(logging.WARN):
        return
    sys.stdout.write('\r%s' % status)
    if status.cur == status.max:
        sys.stdout.write(os.linesep)


def BOOLEAN(v):
    """Test if a value is a boolena."""
    assert v in (True, False)


def LIST(v):
    """Test if a value is a list."""
    assert hasattr(v, '__iter__')


def LIST_NONZERO_INT(v):
    """Test to see if all values in a list are > 0."""
    assert all(x > 0 for x in v)


def INT(min=0, max=None):
    """Test if int is in range."""
    def checkint(v):
        assert isinstance(v, int)
        assert v >= min
        if max is not None:
            assert v <= max

    return checkint


def STRING(v):
    """Test if value is string."""
    assert isinstance(v, str)


def NTUPLE(size):
    """Check if tupple is of proper size."""
    def checktuple(v):
        assert len(v) == size

    return checktuple


def TONELIST(v):
    """Test if tone is valid."""
    assert all(VALIDTONE(x) for x in v)


class RadioPrompts:
    """Radio prompt strings."""

    info = None
    experimental = None
    pre_download = None
    pre_upload = None
    display_pre_upload_prompt_before_opening_port = True


class RadioFeatures:
    """Radio Feature Flags."""

    _valid_map = {
        # General
        'has_bank_index':       BOOLEAN,
        'has_dtcs':             BOOLEAN,
        'has_rx_dtcs':          BOOLEAN,
        'has_dtcs_polarity':    BOOLEAN,
        'has_mode':             BOOLEAN,
        'has_offset':           BOOLEAN,
        'has_name':             BOOLEAN,
        'has_bank':             BOOLEAN,
        'has_bank_names':       BOOLEAN,
        'has_tuning_step':      BOOLEAN,
        'has_ctone':            BOOLEAN,
        'has_cross':            BOOLEAN,
        'has_infinite_number':  BOOLEAN,
        'has_nostep_tuning':    BOOLEAN,
        'has_comment':          BOOLEAN,
        'has_settings':         BOOLEAN,
        'has_variable_power':   BOOLEAN,
        'has_dynamic_subdevices': BOOLEAN,

        # Attributes
        'valid_modes':          LIST,
        'valid_tmodes':         LIST,
        'valid_duplexes':       LIST,
        'valid_tuning_steps':   LIST_NONZERO_INT,
        'valid_bands':          LIST,
        'valid_skips':          LIST,
        'valid_power_levels':   LIST,
        'valid_characters':     STRING,
        'valid_name_length':    INT(),
        'valid_cross_modes':    LIST,
        'valid_tones':          TONELIST,
        'valid_dtcs_pols':      LIST,
        'valid_dtcs_codes':     LIST,
        'valid_special_chans':  LIST,

        'has_sub_devices':      BOOLEAN,
        'memory_bounds':        NTUPLE(2),
        'can_odd_split':        BOOLEAN,
        'can_delete':           BOOLEAN,

        # D-STAR
        'requires_call_lists':  BOOLEAN,
        'has_implicit_calls':   BOOLEAN,
    }

    def __setattr__(self, name, val):
        """Set attribute name to value."""
        if name.startswith('_'):
            self.__dict__[name] = val
            return
        elif name not in self._valid_map:
            raise ValueError("No such attribute `%s'" % name)

        try:
            self._valid_map[name](val)
        except AssertionError:
            raise ValueError('Invalid value %r for attribute %r' % (
                val, name))

        self.__dict__[name] = val

    def __getattr__(self, name):
        """Return named attribute value."""
        raise AttributeError('pylint is confused by RadioFeatures')

    def init(self, attribute, default, doc=None):
        """Initialize a feature flag @attribute.

        Using default value @default and documentation string @doc.
        """
        self.__setattr__(attribute, default)
        self.__docs[attribute] = doc

    def get_doc(self, attribute):
        """Return the description of @attribute."""
        return self.__docs[attribute]

    def __init__(self):
        """Construct object."""
        self.__docs = {}
        self.init('has_bank_index', False,
                  'Indicates that memories in a bank can be stored in ' +
                  'an order other than in main memory')
        self.init('has_dtcs', True,
                  'Indicates that DTCS tone mode is available')
        self.init('has_rx_dtcs', False,
                  'Indicates that radio can use two different ' +
                  'DTCS codes for rx and tx')
        self.init('has_dtcs_polarity', True,
                  'Indicates that the DTCS polarity can be changed')
        self.init('has_mode', True,
                  'Indicates that multiple emission modes are supported')
        self.init('has_offset', True,
                  'Indicates that the TX offset memory property is supported')
        self.init('has_name', True,
                  'Indicates that an alphanumeric memory name is supported')
        self.init('has_bank', True,
                  'Indicates that memories may be placed into banks')
        self.init('has_bank_names', False,
                  'Indicates that banks may be named')
        self.init('has_tuning_step', True,
                  'Indicates that memories store their tuning step')
        self.init('has_ctone', True,
                  'Indicates that the radio keeps separate tone frequencies ' +
                  'for repeater and CTCSS operation')
        self.init('has_cross', False,
                  'Indicates that the radios supports different tone modes ' +
                  'on transmit and receive')
        self.init('has_infinite_number', False,
                  'Indicates that the radio is not constrained in the ' +
                  'number of memories that it can store')
        self.init('has_nostep_tuning', False,
                  'Indicates that the radio does not require a valid ' +
                  'tuning step to store a frequency')
        self.init('has_comment', False,
                  'Indicates that the radio supports storing a comment ' +
                  'with each memory')
        self.init('has_settings', False,
                  'Indicates that the radio supports general settings')
        self.init('has_variable_power', False,
                  'Indicates the radio supports any power level between the '
                  'min and max in valid_power_levels')
        self.init('has_dynamic_subdevices', False,
                  'Indicates the radio has a non-static list of subdevices')

        self.init('valid_modes', list(MODES),
                  'Supported emission (or receive) modes')
        self.init('valid_tmodes', [],
                  'Supported tone squelch modes')
        self.init('valid_duplexes', ['', '+', '-'],
                  'Supported duplex modes')
        self.init('valid_tuning_steps', list(COMMON_TUNING_STEPS),
                  'Supported tuning steps')
        self.init('valid_bands', [],
                  'Supported frequency ranges')
        self.init('valid_skips', ['', 'S'],
                  'Supported memory scan skip settings')
        self.init('valid_power_levels', [],
                  'Supported power levels')
        self.init('valid_characters', CHARSET_UPPER_NUMERIC,
                  "Supported characters for a memory's alphanumeric tag")
        self.init('valid_name_length', 6,
                  "The maximum number of characters in a memory's " +
                  'alphanumeric tag')
        self.init('valid_cross_modes', list(CROSS_MODES),
                  'Supported tone cross modes')
        self.init('valid_tones', list(TONES),
                  'Support Tones')
        self.init('valid_dtcs_pols', ['NN', 'RN', 'NR', 'RR'],
                  'Supported DTCS polarities')
        self.init('valid_dtcs_codes', list(DTCS_CODES),
                  'Supported DTCS codes')
        self.init('valid_special_chans', [],
                  'Supported special channel names')

        self.init('has_sub_devices', False,
                  'Indicates that the radio behaves as two semi-independent ' +
                  'devices')
        self.init('memory_bounds', (0, 1),
                  'The minimum and maximum channel numbers')
        self.init('can_odd_split', False,
                  'Indicates that the radio can store an independent ' +
                  'transmit frequency')
        self.init('can_delete', True,
                  'Indicates that the radio can delete memories')
        self.init('requires_call_lists', True,
                  '[D-STAR] Indicates that the radio requires all callsigns ' +
                  'to be in the master list and cannot be stored ' +
                  'arbitrarily in each memory channel')
        self.init('has_implicit_calls', False,
                  '[D-STAR] Indicates that the radio has an implied ' +
                  'callsign at the beginning of the master URCALL list')

    def is_a_feature(self, name):
        """Return True if @name is a valid feature flag name."""
        return name in self._valid_map

    def __getitem__(self, name):
        """Return an item."""
        return self.__dict__[name]


class Radio(object):
    """Base class for all Radio drivers."""

    VENDOR: str = 'Unknown'
    MODEL: str = 'Unknown'
    VARIANT: str = ''
    ALIAS: tuple[str, str, str] = ('', '', '',)
    BAUD_RATE: int = 9600
    # Whether or not we should use RTS/CTS flow control
    HARDWARE_FLOW: bool = False
    # Whether or not we should assert DTR when opening the serial port
    WANTS_DTR: bool = True
    # Whether or not we should assert RTS when opening the serial port
    WANTS_RTS: bool = True
    ALIASES: list[tuple] = []
    NEEDS_COMPAT_SERIAL: bool = False
    FORMATS: list[str] = []

    def status_fn(self, status):
        """Deliver @status to the UI."""
        console_status(status)

    def __init__(self, pipe):
        """Create object by reading radio."""
        self.errors = []
        self.pipe = pipe

    def get_features(self) -> RadioFeatures:
        """Return a RadioFeatures object for this radio."""
        return RadioFeatures()

    @classmethod
    def get_name(cls) -> str:
        """Return a printable name for this radio."""
        return '%s %s' % (cls.VENDOR, cls.MODEL)

    @classmethod
    def get_prompts(cls) -> RadioPrompts:
        """Return a set of strings for use in prompts."""
        return RadioPrompts()

    def set_pipe(self, pipe) -> None:
        """Set the serial object to be used for communications."""
        self.pipe = pipe

    def get_memory(self, number: int | str) -> Memory:
        """Return a Memory object for the memory at location @number.

        Constructs and returns a generic Memory object for the given location
        in the radio's memory. The memory should accurately represent what is
        actually stored in the radio as closely as possible. If the radio
        does not support changing some attributes of the location in question,
        the Memory.immutable list should be set appropriately.

        NB: No changes to the radio's memory should occur as a result of
        calling get_memory().
        """
        raise NotImplementedError()

    def erase_memory(self, number: int | str) -> None:
        """Erase memory at location @number."""
        mem = Memory()
        if isinstance(number, str):
            mem.extd_number = number
        else:
            mem.number = number
        mem.empty = True
        self.set_memory(mem)

    def get_memories(self, lo=None, hi=None):
        """Get all the memories between @lo and @hi."""
        pass

    def set_memory(self, memory: Memory) -> None:
        """Set the memory object @memory.

        This method should copy generic attributes from @memory to the
        radio's memory. It should not modify @memory and it should reproduce
        the generic attributes on @memory in the radio's memory as faithfully
        as the radio allows. Attributes that can't be copied exactly should
        be warned in validate_memory() with ValidationWarnings if a
        substitution will be made, or ValidationError if truly incompatible.
        In the latter case, set_memory() will not be called.
        """
        raise NotImplementedError()

    def get_mapping_models(self):
        """Return a list of MappingModel objects (or an empty list)."""
        if hasattr(self, 'get_bank_model'):
            # FIXME: Backwards compatibility for old bank models
            bank_model = self.get_bank_model()
            if bank_model:
                return [bank_model]
        return []

    def get_raw_memory(self, number: int | str) -> str:
        """Return a raw string describing the memory at @number."""
        return 'Memory<%r>' % number

    def filter_name(self, name: str) -> str:
        """Filter @name to just the length and characters supported."""
        rf = self.get_features()
        if rf.valid_characters == rf.valid_characters.upper():
            # Radio only supports uppercase, so help out here
            name = name.upper()
        return ''.join(x for x in name[:rf.valid_name_length]
                       if x in rf.valid_characters)

    def get_sub_devices(self) -> list[tuple]:
        """Return a list of sub-device Radio objects.

        if RadioFeatures.has_sub_devices is True.
        """
        return []

    def validate_memory(self, mem: Memory) -> list[str]:
        """Return a list of warnings and errors.

        that will be encountered if trying to set @mem on the current radio.
        """
        rf = self.get_features()
        return rf.validate_memory(mem)

    def get_settings(self):
        """Return a RadioSettings list.

        That contains one or more RadioSettingGroup or RadioSetting objects.
        These represent general setting knobs and dials that can be adjusted
        on the radio. If this function is implemented, the has_settings
        RadioFeatures flag should be True and set_settings() must be
        implemented as well.
        """
        pass

    def set_settings(self, settings):
        """Accept the top-level RadioSettingGroup.

        returned from get_settings() and adjusts the values in the radio
        accordingly. This function expects the entire RadioSettingGroup
        hierarchy returned from get_settings().
        If this function is implemented, the has_settings RadioFeatures flag
        should be True and get_settings() must be implemented as well.
        """
        pass

    @classmethod
    def supports_format(cls, fmt: str) -> bool:
        """Return true if file format @fmt is supported by this radio.

        This really should not be overridden by implementations
        without a good reason (like excluding one).
        """
        return fmt in cls.FORMATS

    def check_set_memory_immutable_policy(self, existing: Memory, new: Memory):
        """Check whether or not a new memory will violate policy.

        Some radios have complex requirements for which fields of which
        memories can be modified at any given point. For the most part, radios
        require certain physical memory slots to have immutable fields
        (such as labels on call channels), and this default implementation
        checks that policy. However, other radios have more fine-grained
        rules in order to comply with FCC type acceptance, which requires
        overriding this behavior.

        ** This should almost never be overridden in your driver.

        ** This must not communicate with the radio, if implemented on a live-
           mode driver.
        """
        for field in existing.immutable:
            if getattr(existing, field) != getattr(new, field):
                raise ImmutableValueError(
                    'Field %s is not mutable on this memory' % field)
