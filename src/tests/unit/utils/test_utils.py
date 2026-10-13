"""Tests for shared radio utility functions and memory mappings."""

from types import SimpleNamespace

from chirp_web.errors import InvalidDataError
from chirp_web.utils.memory import Memory
from chirp_web.utils.utils import (
    MemoryMapping,
    StaticBankModel,
    Status,
    _name,
    in_range,
    is_version_newer,
    mem_from_text,
    mem_to_text,
    name16,
    name6,
    name8,
    required_step,
    sanitize_string,
    split_to_offset,
    split_tone_decode,
    split_tone_encode,
)

import pytest


@pytest.mark.parametrize(
    ('rx', 'tx', 'duplex', 'offset'),
    [
        (146520000, 146920000, '+', 400000),
        (146920000, 146520000, '-', 400000),
        (146520000, 146520000, '', 0),
        (146520000, 446520001, 'split', 446520001),
    ],
)
def test_split_to_offset(rx, tx, duplex, offset):
    """Represent paired receive/transmit frequencies as memory settings."""
    memory = Memory()
    split_to_offset(memory, rx, tx)

    assert memory.freq == rx
    assert memory.duplex == duplex
    assert memory.offset == offset


@pytest.mark.parametrize(
    ('tx', 'rx', 'tmode', 'cross_mode', 'rtone', 'ctone', 'dtcs', 'rx_dtcs'),
    [
        (('', None, None), ('', None, None), '', 'Tone->Tone',
         88.5, 88.5, 23, 23),
        (('Tone', 100.0, None), ('', None, None), 'Tone', 'Tone->Tone',
         100.0, 88.5, 23, 23),
        (('Tone', 100.0, None), ('Tone', 100.0, None), 'TSQL',
         'Tone->Tone', 88.5, 100.0, 23, 23),
        (('DTCS', 245, 'R'), ('DTCS', 245, 'N'), 'DTCS',
         'Tone->Tone', 88.5, 88.5, 245, 23),
        (('Tone', 103.5, None), ('DTCS', 245, 'R'), 'Cross',
         'Tone->DTCS', 103.5, 88.5, 23, 245),
    ],
)
def test_split_tone_decode_and_encode(
        tx, rx, tmode, cross_mode, rtone, ctone, dtcs, rx_dtcs):
    """Decode supported tone combinations and encode them losslessly."""
    memory = Memory()
    split_tone_decode(memory, tx, rx)

    assert memory.tmode == tmode
    assert memory.cross_mode == cross_mode
    assert memory.rtone == rtone
    assert memory.ctone == ctone
    assert memory.dtcs == dtcs
    assert memory.rx_dtcs == rx_dtcs
    assert split_tone_encode(memory) == (tx, rx)


def test_name_helpers_pad_truncate_and_control_case():
    """Name helpers apply their individual default casing rules."""
    assert _name('abc', 5, True) == 'ABC  '
    assert name6('abcdefg') == 'ABCDEF'
    assert name8('aB') == 'aB      '
    assert name16('x' * 17) == 'x' * 16


def test_sanitize_string_replaces_invalid_ascii_but_keeps_unicode():
    """Sanitization preserves allowed and non-ASCII characters."""
    assert sanitize_string('AB\n☃', validcharset='AB', replacechar='?') == (
        'AB?☃')
    assert sanitize_string('abc', validcharset='abc') == 'abc'


def test_required_step_success_and_unsupported_frequency():
    """Find a supported step and report frequencies no allowed step reaches."""
    assert required_step(146520000) == 5.0
    assert required_step(146521000, allowed=[1.0]) == 1.0
    with pytest.raises(InvalidDataError, match='Unable to find'):
        required_step(146520501, allowed=[])


class FakeRadio:
    """Radio stub for static bank tests."""

    def __init__(self, bounds):
        """Initialize class."""
        self.features = SimpleNamespace(memory_bounds=bounds)

    def get_features(self):
        """Return radio features."""
        return self.features

    def get_memory(self, number):
        """Return memory."""
        return Memory(number=number)


def test_static_bank_model_partitions_all_memories_evenly():
    """Partition non-divisible memory bounds without losing channels."""
    radio = FakeRadio((1, 11))
    model = StaticBankModel(radio, banks=3)
    banks = model.get_mappings()

    assert model.get_num_mappings() == 3
    assert [[mem.number for mem in model.get_mapping_memories(bank)]
            for bank in banks] == [
        [1, 2, 3], [4, 5, 6, 7], [8, 9, 10, 11],
    ]
    assert model.get_memory_mappings(Memory(number=7)) == [banks[1]]
    assert model.get_memory_mappings(Memory(number=11)) == [banks[2]]


def test_static_bank_model_handles_more_banks_than_memories():
    """Assign each available memory to the corresponding nonempty bank."""
    model = StaticBankModel(FakeRadio((0, 1)), banks=4)
    banks = model.get_mappings()

    assert model.get_mapping_memories(banks[0]) == []
    assert [
        memory.number
        for memory in model.get_mapping_memories(banks[1])
    ] == [0]
    assert model.get_mapping_memories(banks[2]) == []
    assert [
        memory.number
        for memory in model.get_mapping_memories(banks[3])
    ] == [1]
    assert model.get_memory_mappings(Memory(number=0)) == [banks[1]]


@pytest.mark.parametrize('banks', [0, -1, 1.5, True])
def test_static_bank_model_rejects_invalid_bank_count(banks):
    """Require a positive integer number of static banks."""
    with pytest.raises(ValueError, match='positive integer'):
        StaticBankModel(FakeRadio((0, 9)), banks=banks)


@pytest.mark.parametrize('bounds', [(0, -1), (0.0, 9), (False, 9)])
def test_static_bank_model_rejects_invalid_memory_bounds(bounds):
    """Require ordered integer memory bounds for range partitioning."""
    with pytest.raises(ValueError, match='memory_bounds'):
        StaticBankModel(FakeRadio(bounds), banks=2)


def test_static_bank_model_rejects_unknown_bank_and_out_of_range_memory():
    """Report invalid mapping requests instead of indexing arbitrary banks."""
    model = StaticBankModel(FakeRadio((0, 9)), banks=2)

    with pytest.raises(ValueError, match='Unknown bank'):
        model.get_mapping_memories(MemoryMapping(model, 3, 'Invalid'))
    with pytest.raises(ValueError, match='outside bounds'):
        model.get_memory_mappings(Memory(number=10))
    with pytest.raises(NotImplementedError, match='fixed banks'):
        model.add_memory_to_mapping(Memory(), model.get_mappings()[0])


def test_memory_mapping_equality_and_string_representations():
    """Compare mapping indices and provide readable identifiers."""
    model = StaticBankModel(FakeRadio((0, 9)), banks=2)
    first = model.get_mappings()[0]
    same_index = MemoryMapping(model, 1, 'Different label')

    assert first == same_index
    assert first != object()
    assert str(first) == 'Bank'
    assert repr(first) == 'StaticBank-1'


def test_status_formats_progress_and_zero_maximum():
    """Format ordinary progress and handle an empty progress range."""
    status = Status()
    status.cur = 50
    status.max = 100
    status.msg = 'Reading'
    assert str(status) == '|=====     | 50.0% Reading'

    status.max = 0
    assert str(status) == '|??????????| 0.0% Reading'


def test_mem_text_round_trip():
    """Parse and format an ordinary frequency, offset, and CTCSS tone."""
    memory = mem_from_text('146.520 +0.600 100.0')

    assert memory.freq == 146520000
    assert memory.duplex == '+'
    assert memory.offset == 600000
    assert memory.tmode == 'Tone'
    assert mem_to_text(memory) == '[146.520000/+0.600/100.0]'


def test_mem_from_text_rejects_missing_frequency():
    """Require at least one recognizable frequency."""
    with pytest.raises(ValueError, match='Unable to find a frequency'):
        mem_from_text('no frequency here')


def test_in_range_includes_boundaries_and_empty_ranges():
    """Check inclusive endpoints and an empty range collection."""
    assert in_range(10, [(10, 20)])
    assert in_range(20, [(10, 20)])
    assert not in_range(21, [(10, 20)])
    assert not in_range(10, [])


def test_is_version_newer_compares_candidate_to_installed(monkeypatch):
    """Compare incoming metadata against the installed package version."""
    import chirp_web.__version__ as version_module

    monkeypatch.setattr(version_module, 'version', '1.9.0')
    assert is_version_newer('2.0.0')
    assert not is_version_newer('1.8.9')
    assert is_version_newer('daily-20261005')
