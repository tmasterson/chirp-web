

"""Shared radio utilities and radio mapping implementations."""

import base64
import json
import logging
import re
import sys

from chirp_web import errors, memmap
from chirp_web.__version__ import version
from chirp_web.errors import ImmutableValueError
from chirp_web.interfaces import DetectableInterface
from chirp_web.utils.common import CHARSET_ASCII, format_freq, parse_freq
from chirp_web.utils.memory import Memory
from chirp_web.utils.radio import Radio


LOG = logging.getLogger(__name__)


class MappingModel(object):
    """Base class for a memory mapping model."""

    def __init__(self, radio, name):
        """Construct mapping for this model of radio."""
        self._radio = radio
        self._name = name

    def get_name(self):
        """Return model name."""
        return self._name

    def get_num_mappings(self):
        """Return the number of mappings in the model.

        should be callable without consulting the radio
        """
        raise NotImplementedError()

    def get_mappings(self):
        """Return a list of mappings."""
        raise NotImplementedError()

    def add_memory_to_mapping(self, memory, mapping):
        """Add @memory to @mapping."""
        raise NotImplementedError()

    def remove_memory_from_mapping(self, memory, mapping):
        """Remove @memory from @mapping.

        Shall raise exception if @memory is not in @bank
        """
        raise NotImplementedError()

    def get_mapping_memories(self, mapping):
        """Return a list of memories in @mapping."""
        raise NotImplementedError()

    def get_memory_mappings(self, memory):
        """Return a list of mappings that @memory is in."""
        raise NotImplementedError()


class MemoryMapping(object):
    """Base class for a memory mapping."""

    def __init__(self, model, index, name):
        """Construct object."""
        self._model = model
        self._index = index
        self._name = name

    def __str__(self):
        """Return name of this object."""
        return self.get_name()

    def __repr__(self):
        """Stringify entire object."""
        return '%s-%s' % (self.__class__.__name__, self._index)

    def get_name(self):
        """Return the mapping name."""
        return self._name

    def get_index(self):
        """Return the immutable index (string or int)."""
        return self._index

    def __eq__(self, other):
        """Test to see if other equals this oject."""
        if not isinstance(other, MemoryMapping):
            return NotImplemented
        return self.get_index() == other.get_index()


class Bank(MemoryMapping):
    """Base class for a radio's Bank."""


class NamedBank(Bank):
    """A bank that can have a name."""

    def set_name(self, name):
        """Change the user-adjustable bank name."""
        self._name = name


class BankModel(MappingModel):
    """A bank model where one memory is in zero or one banks at any point."""

    def __init__(self, radio, name='Banks'):
        """Construct object."""
        super(BankModel, self).__init__(radio, name)


class StaticBank(Bank):
    """Class for a static bank."""

    pass


class StaticBankModel(BankModel):
    """A BankModel that shows a static mapping but does not allow changes."""

    MSG = 'This radio has fixed banks and does not allow reassignment'
    channelAlwaysHasBank = True

    def __init__(self, radio, name='Banks', banks=10):
        """Construct object."""
        if not isinstance(banks, int) or isinstance(banks, bool) or banks <= 0:
            raise ValueError('banks must be a positive integer')
        super().__init__(radio, name=name)
        self._num_banks = banks
        self._rf = radio.get_features()
        lo, hi = self._rf.memory_bounds
        if (not isinstance(lo, int) or isinstance(lo, bool) or
                not isinstance(hi, int) or isinstance(hi, bool) or hi < lo):
            raise ValueError(
                'memory_bounds must be an ordered pair of integers')
        self._banks = [
            StaticBank(self, i + 1, 'Bank')
            for i in range(self._num_banks)
        ]

    def get_num_mappings(self):
        """Return number of mappings."""
        return self._num_banks

    def get_mappings(self):
        """Return mappings."""
        return self._banks

    def get_mapping_memories(self, bank):
        """Return the memories in a bank."""
        lo, hi = self._rf.memory_bounds
        index = bank.get_index() - 1
        if not 0 <= index < self._num_banks:
            raise ValueError(f'Unknown bank index: {bank.get_index()}')
        total = hi - lo + 1
        start = lo + (index * total // self._num_banks)
        stop = lo + ((index + 1) * total // self._num_banks)
        return [self._radio.get_memory(number)
                for number in range(start, stop)]

    def get_memory_mappings(self, memory):
        """Return the mappings a memory is in."""
        lo, hi = self._rf.memory_bounds
        if not lo <= memory.number <= hi:
            raise ValueError(
                f'Memory number is outside bounds: {memory.number}')
        total = hi - lo + 1
        index = (((memory.number - lo + 1) * self._num_banks) - 1) // total
        return [self._banks[index]]

    def remove_memory_from_mapping(self, memory, mapping):
        """Remove a memory from a mapping."""
        raise NotImplementedError(self.MSG)

    def add_memory_to_mapping(self, memory, mapping):
        """Add a memory to a mapping."""
        raise NotImplementedError(self.MSG)


class MTOBankModel(BankModel):
    """A bank model where one memory can be in multiple banks at once."""

    pass


class ExternalMemoryProperties:
    """A mixin class that provides external memory property support.

    This is for use by drivers that have some way of storing additional
    memory properties externally (i.e. in metadata or a separate region)
    that cannot be loaded/updated during get_memory()/set_memory().
    Implementing this is much less ideal than supporting those properties
    directly, so this should only be used when absolutely necessary.
    """

    def get_memory_extra(self, memory):
        """Update @memory with extra fields.

        This is called after get_memory() and is passed the result
        for augmentation from external storage.
        """
        return memory

    def set_memory_extra(self, memory):
        """Update external storage of properties from @memory.

        This is called after set_memory() with the same memory object
        to record additional properties in external storage.
        """
        pass

    def erase_memory_extra(self, number):
        """Erase external storage for @memory.

        This is called after erase_memory() to clear external storage
        for memory @number.
        """
        pass

    def link_device_metadata(self, devices):
        """Link sub-device metadata with parent.

        This is called after get_sub_devices() to make sure that the
        sub-device instances use a reference into the main radio's
        metadata. In most cases, this does not need to be overridden.
        """
        # Link metadata of the sub-devices into the main by variant name
        # so that they are both included in a later save of the parent.
        for sub in devices:
            self._metadata.setdefault(sub.VARIANT, {})
            sub._metadata = self._metadata[sub.VARIANT]


class FileBackedRadio(Radio):
    """A file-backed radio stores its data in a file."""

    FILE_EXTENSION = 'dat'

    def save(self, filename):
        """Save the radio's memory map to @filename."""
        pass

    def load(self, filename):
        """Load the radio's memory map object from @filename."""
        pass


def class_detected_models_attribute(cls):
    """Return detected models for a radio."""
    return 'DETECTED_MODELS_%s' % cls.__name__


class CloneModeRadio(FileBackedRadio, ExternalMemoryProperties,
                     DetectableInterface):
    """Class for a clone-mode radio.

    A clone-mode radio does a full memory dump in and out and we store
    an image of the radio into an image file.
    """

    FILE_EXTENSION = 'img'
    MAGIC = b'\x00\xffchirp\xeeimg\x00\x01'

    _memsize = 0

    def __init__(self, pipe):
        """Construct radio model."""
        self.errors = []
        self._mmap = None
        self._memobj = None
        self._metadata = {}

        if isinstance(pipe, str):
            self.pipe = None
            self.load_mmap(pipe)
        elif isinstance(pipe, memmap.MemoryMapBytes):
            self.pipe = None
            self._mmap = pipe
            self.process_mmap()
        else:
            FileBackedRadio.__init__(self, pipe)

    def get_memsize(self):
        """Return the radio's memory size."""
        return self._memsize

    @classmethod
    def match_model(cls, filedata, filename):
        """Return True if this radio driver handles the represented model."""
        # Unless the radio driver does something smarter, claim
        # support if the data is the same size as our memory.
        # Ideally, each radio would perform an intelligent analysis to
        # make this determination to avoid model conflicts with
        # memories of the same size.
        return cls._memsize and len(filedata) == cls._memsize

    def sync_in(self):
        """Initiate a radio-to-PC clone operation."""
        pass

    def sync_out(self):
        """Initiate a PC-to-radio clone operation."""
        pass

    def save(self, filename):
        """Save the radio's memory map to @filename."""
        self.save_mmap(filename)

    def load(self, filename):
        """Load the radio's memory map object from @filename."""
        self.load_mmap(filename)

    def process_mmap(self):
        """Process a newly-loaded or downloaded memory map."""
        pass

    @classmethod
    def _strip_metadata(cls, raw_data):
        try:
            idx = raw_data.index(cls.MAGIC)
        except ValueError:
            LOG.debug('Image data has no metadata blob')
            return raw_data, {}

        # Find the beginning of the base64 blob
        raw_metadata = raw_data[idx + len(cls.MAGIC):]
        metadata = {}
        try:
            metadata = json.loads(base64.b64decode(raw_metadata).decode())
        except ValueError as e:
            LOG.error('Failed to parse decoded metadata blob: %s' % e)
        except TypeError as e:
            LOG.error('Failed to decode metadata blob: %s' % e)

        if metadata:
            LOG.debug('Loaded metadata: %s' % metadata)

        return raw_data[:idx], metadata

    def _make_metadata(self):
        # Always generate these directly from our in-memory state
        base = {
            'rclass': self.__class__.__name__,
            'vendor': self.VENDOR,
            'model': self.MODEL,
            'variant': self.VARIANT,
            'chirp_version': version,
        }

        # Any other properties take a back seat to the above
        extra = {k: v for k, v in self._metadata.items() if k not in base}
        extra.update(base)

        return base64.b64encode(json.dumps(extra).encode())

    def load_mmap(self, filename):
        """Load the radio's memory map from @filename."""
        mapfile = open(filename, 'rb')
        data = mapfile.read()
        if self.MAGIC in data:
            data, self._metadata = self._strip_metadata(data)
            if ('chirp_version' in self._metadata and
                    is_version_newer(self._metadata.get('chirp_version'))):
                LOG.warning('Image is from version %s but we are %s' % (
                    self._metadata.get('chirp_version'), version))
        if self.NEEDS_COMPAT_SERIAL:
            self._mmap = memmap.MemoryMap(data)
        else:
            self._mmap = memmap.MemoryMapBytes(bytes(data))
        mapfile.close()
        self.process_mmap()

    def save_mmap(self, filename):
        """Save a map to a fiel.

        try to open a file and write to it
        If IOError raise a File Access Error Exception
        """
        try:
            mapfile = open(filename, 'wb')
            mapfile.write(self._mmap.get_byte_compatible().get_packed())
            if filename.lower().endswith('.img'):
                mapfile.write(self.MAGIC)
                mapfile.write(self._make_metadata())
            mapfile.close()
        except IOError:
            raise Exception('File Access Error')

    def get_mmap(self):
        """Return the radio's memory map object."""
        return self._mmap

    @property
    def metadata(self):
        """Return the metadata."""
        return dict(self._metadata)

    @metadata.setter
    def metadata(self, values):
        self._metadata.update(values)

    def get_memory_extra(self, memory):
        """Return memory extra."""
        rf = self.get_features()
        if not rf.has_comment and isinstance(memory.number, int):
            self._metadata.setdefault('mem_extra', {})
            try:
                memory.comment = self._metadata['mem_extra'].get(
                    '%04i_comment' % memory.number, '')
            except ImmutableValueError:
                pass
        return memory

    def set_memory_extra(self, memory):
        """Set memory extra."""
        rf = self.get_features()
        if not rf.has_comment and isinstance(memory.number, int):
            self._metadata.setdefault('mem_extra', {})
            key = '%04i_comment' % memory.number
            if not memory.comment:
                self._metadata['mem_extra'].pop(key, None)
            else:
                self._metadata['mem_extra'][key] = memory.comment

    def erase_memory_extra(self, number):
        """Erase memory extra."""
        rf = self.get_features()
        if not rf.has_comment and isinstance(number, int):
            self._metadata.setdefault('mem_extra', {})
            self._metadata['mem_extra'].pop('%04i_comment' % number, None)


class LiveRadio(Radio, DetectableInterface):
    """Base class for all Live-Mode radios."""

    pass


class NetworkSourceRadio(Radio):
    """Base class for all radios based on a network source."""

    def do_fetch(self):
        """Fetch the source data from the network."""
        pass


class IcomDstarSupport:
    """Base interface for radios supporting Icom's D-STAR technology."""

    MYCALL_LIMIT = (1, 1)
    URCALL_LIMIT = (1, 1)
    RPTCALL_LIMIT = (1, 1)

    def get_urcall_list(self):
        """Return a list of URCALL callsigns."""
        return []

    def get_repeater_call_list(self):
        """Return a list of RPTCALL callsigns."""
        return []

    def get_mycall_list(self):
        """Return a list of MYCALL callsigns."""
        return []

    def set_urcall_list(self, calls):
        """Set the URCALL callsign list."""
        pass

    def set_repeater_call_list(self, calls):
        """Set the RPTCALL callsign list."""
        pass

    def set_mycall_list(self, calls):
        """Set the MYCALL callsign list."""
        pass


class ExperimentalRadio:
    """Interface for experimental radios."""

    @classmethod
    def get_experimental_warning(cls):
        """Return warning."""
        return ("This radio's driver is marked as experimental and may " +
                'be unstable or unsafe to use.')


class Status:
    """Clone status object for conveying clone progress to the UI."""

    name = 'Job'
    msg = 'Unknown'
    max = 100
    cur = 0

    def __str__(self):
        """Return a usable string for this radio."""
        try:
            pct = (self.cur / float(self.max)) * 100
            nticks = int(pct) // 10
            ticks = '=' * nticks
        except (ValueError, ZeroDivisionError):
            pct = 0.0
            ticks = '?' * 10

        return '|%-10s| %2.1f%% %s' % (ticks, pct, self.msg)


def is_fractional_step(freq):
    """Return True if @freq requires a 12.5 kHz or 6.25 kHz step."""
    return not is_5_0(freq) and (is_12_5(freq) or is_6_25(freq))


def is_5_0(freq):
    """Return True if @freq is reachable by a 5 kHz step."""
    return (freq % 5000) == 0


def is_10_0(freq):
    """Return True if @freq is reachable by a 10 kHz step."""
    return (freq % 10000) == 0


def is_12_5(freq):
    """Return True if @freq is reachable by a 12.5 kHz step."""
    return (freq % 12500) == 0


def is_6_25(freq):
    """Return True if @freq is reachable by a 6.25 kHz step."""
    return (freq % 6250) == 0


def is_2_5(freq):
    """Return True if @freq is reachable by a 2.5 kHz step."""
    return (freq % 2500) == 0


def is_8_33(freq):
    """Return True if @freq is reachable by a 8.33 kHz step."""
    return (freq % 25000) in [0, 8330, 16660]


def is_1_0(freq):
    """Return True if @freq is reachable by a 1.0 kHz step."""
    return (freq % 1000) == 0


def is_0_5(freq):
    """Return True if @freq is reachable by a 0.5 kHz step."""
    return (freq % 500) == 0


def make_is(stephz):
    """Return somthing."""
    def validator(freq):
        return freq % stephz == 0
    return validator


def required_step(freq, allowed=None):
    """Return the simplest tuning step that is required to reach @freq."""
    if allowed is None:
        allowed = [5.0, 10.0, 12.5, 6.25, 2.5, 8.33]

    # These should be in order of most common to least common
    steps = {
        5.0: make_is(5000),
        10.0: make_is(10000),
        12.5: make_is(12500),
        6.25: make_is(6250),
        2.5: make_is(2500),
        1.0: make_is(1000),
        0.5: make_is(500),
        0.25: make_is(250),
        8.33: is_8_33,
    }

    # Try the above "standard" steps first in order
    required_step = None
    for step, validate in steps.items():
        if step in allowed and validate(freq):
            return step
        elif validate(freq) and required_step is None:
            required_step = step

    # Try any additional steps in the allowed list
    for step in allowed:
        if step in steps:
            # Already tried
            continue
        if make_is(int(step * 1000))(freq):
            LOG.debug('Chose non-standard step %s for %s' % (
                step, format_freq(freq)))
            return step

    if required_step is not None:
        raise errors.InvalidDataError((
            'Frequency %s requires step %.2f, '
            'which is not supported') % (
                format_freq(freq), required_step))
    else:
        raise errors.InvalidDataError('Unable to find a supported ' +
                                      'tuning step for %s' % format_freq(freq))


def fix_rounded_step(freq):
    """Return corrected step.

    Some radios imply the last bit of 12.5 kHz and 6.25 kHz step
    frequencies. Take the base @freq and return the corrected one.
    """
    try:
        required_step(freq)
        return freq
    except errors.InvalidDataError:
        pass

    try:
        required_step(freq + 500)
        return freq + 500
    except errors.InvalidDataError:
        pass

    try:
        required_step(freq + 250)
        return freq + 250
    except errors.InvalidDataError:
        pass

    try:
        required_step(freq + 750)
        return float(freq + 750)
    except errors.InvalidDataError:
        pass

    try:
        required_step(freq + 330)
        return float(freq + 330)
    except errors.InvalidDataError:
        pass

    try:
        required_step(freq + 660)
        return float(freq + 660)
    except errors.InvalidDataError:
        pass

    raise errors.InvalidDataError('Unable to correct rounded frequency ' +
                                  format_freq(freq))


def _name(name, size, just_upper):
    """Justify @name to @size, optionally converting to all uppercase."""
    if just_upper:
        name = name.upper()
    return name.ljust(size)[:size]


def name6(name, just_upper=True):
    """6-char name."""
    return _name(name, 6, just_upper)


def name8(name, just_upper=False):
    """8-char name."""
    return _name(name, 8, just_upper)


def name16(name, just_upper=False):
    """16-char name."""
    return _name(name, 16, just_upper)


def to_GHz(val):
    """Convert @val in GHz to Hz."""
    return val * 1000000000


def to_MHz(val):
    """Convert @val in MHz to Hz."""
    return val * 1000000


def to_kHz(val):
    """Convert @val in kHz to Hz."""
    return val * 1000


def from_GHz(val):
    """Convert @val in Hz to GHz."""
    return val // 100000000


def from_MHz(val):
    """Convert @val in Hz to MHz."""
    return val // 100000


def from_kHz(val):
    """Convert @val in Hz to kHz."""
    return val // 100


def split_to_offset(mem, rxfreq, txfreq):
    """Set the freq, offset, and duplex fields of a memory.

    This isbased on a separate rx/tx frequency.
    """
    mem.freq = rxfreq
    if abs(txfreq - rxfreq) > to_MHz(70):
        mem.offset = txfreq
        mem.duplex = 'split'
    else:
        offset = txfreq - rxfreq
        if offset < 0:
            mem.duplex = '-'
        elif offset > 0:
            mem.duplex = '+'
        else:
            mem.duplex = ''
        mem.offset = abs(offset)


def split_tone_decode(mem, txtone, rxtone):
    """Set tone mode and valuse.

    Set tone mode and values on @mem based on txtone and rxtone specs like:
    None, None, None
    "Tone", 123.0, None
    "DTCS", 23, "N"
    """
    txmode, txval, txpol = txtone
    rxmode, rxval, rxpol = rxtone

    mem.dtcs_polarity = '%s%s' % (txpol or 'N', rxpol or 'N')

    if not txmode and not rxmode:
        # No tone
        return

    if txmode == 'Tone' and not rxmode:
        mem.tmode = 'Tone'
        mem.rtone = txval
        return

    if txmode == rxmode == 'Tone' and txval == rxval:
        # TX and RX same tone -> TSQL
        mem.tmode = 'TSQL'
        mem.ctone = txval
        return

    if txmode == rxmode == 'DTCS' and txval == rxval:
        mem.tmode = 'DTCS'
        mem.dtcs = txval
        return

    mem.tmode = 'Cross'
    mem.cross_mode = '%s->%s' % (txmode or '', rxmode or '')

    if txmode == 'Tone':
        mem.rtone = txval
    elif txmode == 'DTCS':
        mem.dtcs = txval

    if rxmode == 'Tone':
        mem.ctone = rxval
    elif rxmode == 'DTCS':
        mem.rx_dtcs = rxval


def split_tone_encode(mem):
    """Return tx, rx tones spec.

    Returns TX, RX tone specs based on @mem like:
    None, None, None
    "Tone", 123.0, None
    "DTCS", 23, "N"
    """
    txmode = ''
    rxmode = ''
    txval = None
    rxval = None

    if mem.tmode == 'Tone':
        txmode = 'Tone'
        txval = mem.rtone
    elif mem.tmode == 'TSQL':
        txmode = rxmode = 'Tone'
        txval = rxval = mem.ctone
    elif mem.tmode == 'DTCS':
        txmode = rxmode = 'DTCS'
        txval = rxval = mem.dtcs
    elif mem.tmode == 'Cross':
        txmode, rxmode = mem.cross_mode.split('->', 1)
        if txmode == 'Tone':
            txval = mem.rtone
        elif txmode == 'DTCS':
            txval = mem.dtcs
        if rxmode == 'Tone':
            rxval = mem.ctone
        elif rxmode == 'DTCS':
            rxval = mem.rx_dtcs

    if txmode == 'DTCS':
        txpol = mem.dtcs_polarity[0]
    else:
        txpol = None
    if rxmode == 'DTCS':
        rxpol = mem.dtcs_polarity[1]
    else:
        rxpol = None

    return ((txmode, txval, txpol),
            (rxmode, rxval, rxpol))


def sanitize_string(astring, validcharset=CHARSET_ASCII, replacechar='*'):
    """Replace invalid byte-range characters while preserving wider Unicode."""
    validchars = set(validcharset)
    return ''.join(
        char if ord(char) > 255 or char in validchars else replacechar
        for char in astring
    )


def is_version_newer(version):
    """Return True if version is newer than ours."""

    def get_version(v):
        if v.startswith('daily-'):
            _, stamp = v.split('-', 1)
            ver = (int(stamp),)
        elif '.' in v:
            ver = tuple(int(p) for p in v.split('.'))
        else:
            ver = (0,)
        LOG.debug('Parsed version %r to %r' % (v, ver))
        return ver

    from chirp_web.__version__ import version as current_version

    try:
        candidate_version = get_version(version)
    except ValueError as e:
        LOG.error('Failed to parse version %r: %s' % (version, e))
        candidate_version = (0,)
    try:
        my_version = get_version(current_version)
    except ValueError as e:
        LOG.error('Failed to parse my version %r: %s' % (current_version, e))
        my_version = (0,)

    return candidate_version > my_version


def http_user_agent():
    """Tet system user agent."""
    ver = sys.version_info
    return 'chirp/%s (Python %i.%i.%i on %s)' % (
        version,
        ver.major, ver.minor, ver.micro,
        sys.platform)


def urlretrieve(url, fn):
    """Grab an URL and save it in a specified file."""
    import urllib.request
    import urllib.error

    headers = {
        'User-Agent': http_user_agent(),
    }
    req = urllib.request.Request(url, headers=headers)
    resp = urllib.request.urlopen(req)
    with open(fn, 'wb') as f:
        f.write(resp.read())


def mem_from_text(text):
    """Create a memory class from text."""
    m = Memory()
    freqs = re.findall(r'\b(\d{1,3}\.\d{2,6})\b', text)
    if not freqs:
        raise ValueError('Unable to find a frequency')
    m.freq = parse_freq(freqs[0])
    offset = re.search(r'([+-])\s*(\d\.\d{1,3}|\d)\b', text)
    duplex = re.search(r'\W([+-])\W', text[text.index(freqs[0]):])
    if len(freqs) > 1 and not offset:
        split_to_offset(m, m.freq, parse_freq(freqs[1]))
    else:
        if offset:
            m.duplex = offset.group(1)
            m.offset = parse_freq(offset.group(2))
        # Only look for the first +/- after the frequency, which would be
        # by far the most common arrangement
        if offset is None and duplex:
            m.duplex = duplex.group(1)
    tones = re.findall(r'\b(\d{2,3}\.\d|D\d{3})\b', text)
    if tones and len(tones) <= 2:
        txrx = []
        for val in tones:
            if '.' in val:
                mode = 'Tone'
                tone = float(val)
            elif 'D' in val:
                mode = 'DTCS'
                tone = int(val[1:])
            else:
                continue
            txrx.append((mode, tone, 'N'))
        if len(txrx) == 1:
            txrx.append(('', 88.5, 'N'))
        split_tone_decode(m, txrx[0], txrx[1])

    return m


def mem_to_text(mem):
    """Convert memory to text."""
    pieces = [format_freq(mem.freq)]
    if mem.duplex == 'split':
        pieces.append(format_freq(mem.offset))
    elif mem.duplex in ('-', '+'):
        pieces.append('%s%i.%3.3s' % (mem.duplex,
                                      mem.offset / 1000000,
                                      '%03i' % (mem.offset % 1000000)))
    txrx = split_tone_encode(mem)
    for mode, tone, pol in txrx:
        if mode == 'Tone':
            pieces.append('%.1f' % tone)
        elif mode == 'DTCS':
            pieces.append('D%03i' % tone)
    return '[%s]' % '/'.join(pieces)


def in_range(freq, ranges):
    """Check if freq is in any of the provided ranges."""
    for lo, hi in ranges:
        if lo <= freq <= hi:
            return True
    return False
