"""Tests for the @Memory class."""

# import logging

from chirp_web.errors import InvalidDataError, InvalidMemoryLocation
from chirp_web.utils.memory import Memory

import pytest


def test_create_memory():
    """Test creation of a non-dv memory."""
    m1 = Memory(name='test1')
    assert isinstance(m1, Memory)
    assert m1.name == 'test1'
    assert not m1.dv_mem


def test_create_dv_memory():
    """Test creation of a dv memory."""
    m1 = Memory(name='test1', dv_mem=True)
    assert isinstance(m1, Memory)
    assert m1.name == 'test1'
    assert m1.dv_mem


def test_memory_extras_are_independent():
    """Test extra settings are not shared between memories."""
    first = Memory()
    second = Memory()

    first.extra.append('setting')

    assert second.extra == []


def test_dupe_and_clone():
    """Test copying all memory attributes."""
    source = Memory(number=12, name='source')

    duplicate = source.dupe()
    clone = Memory()
    clone.clone(source)

    assert duplicate.number == clone.number == 12
    assert duplicate.name == clone.name == 'source'
    assert duplicate is not source


def test_repr_includes_memory_values():
    """Test the debug representation includes memory values."""
    memory = Memory(number=3, name='test')

    assert repr(memory).startswith("<Memory 3: freq=0, name='test'")


def test_valid_setting():
    """Test if we can detect invalid setting."""
    m1 = Memory()
    assert not m1.valid_setting('tone', 11)
    m1.immutable.append('rtone')
    assert 'rtone' in m1.immutable
    assert not m1.valid_setting('rtone', 67.0)
    assert not m1.valid_setting('ctone', 11)
    assert not m1.valid_setting('duplex', '*')


def test_csv_round_trip_and_dv_memory():
    """Read back the fields emitted by to_csv, including integer Hz values."""
    memory = Memory(number=12, name='repeater', dv_mem=True)
    memory.freq = 146520000
    memory.offset = 600000
    memory.duplex = '+'
    memory.tmode = 'Tone'
    memory.rtone = 100.0
    memory.ctone = 103.5
    memory.dtcs = 245
    memory.rx_dtcs = 251
    memory.dtcs_polarity = 'NR'
    memory.cross_mode = 'Tone->DTCS'
    memory.mode = 'DV'
    memory.tuning_step = 12.5
    memory.skip = 'S'

    loaded = Memory._from_csv(','.join(memory.to_csv()))

    assert loaded.dv_mem
    assert loaded.number == 12
    assert loaded.name == 'repeater'
    assert loaded.freq == 146520000
    assert loaded.offset == 600000
    assert loaded.duplex == '+'
    assert loaded.tmode == 'Tone'
    assert loaded.rtone == 100.0
    assert loaded.ctone == 103.5
    assert loaded.dtcs == 245
    assert loaded.rx_dtcs == 251
    assert loaded.dtcs_polarity == 'NR'
    assert loaded.cross_mode == 'Tone->DTCS'
    assert loaded.mode == 'DV'
    assert loaded.tuning_step == 12.5
    assert loaded.skip == 'S'


def test_csv_rejects_header_and_short_rows():
    """Reject a header row and incomplete rows with repository errors."""
    with pytest.raises(InvalidMemoryLocation):
        Memory._from_csv('Location,Name,Frequency')
    with pytest.raises(InvalidDataError, match='15 columns'):
        Memory._from_csv('1,short,row')
    with pytest.raises(InvalidDataError, match='15 columns'):
        Memory().really_from_csv(['1', 'short'])


@pytest.mark.parametrize(
    ('index', 'value', 'message'),
    [
        (0, 'bad', 'Location'),
        (2, 'bad', 'Frequency'),
        (3, 'x', 'Duplex'),
        (4, 'bad', 'Offset'),
        (5, 'bad', 'tone mode'),
        (6, 'bad', 'rTone'),
        (7, 'bad', 'cTone'),
        (8, 'bad', 'DTCS code'),
        (9, 'bad', 'DtcsPolarity'),
        (10, 'bad', 'DTCS Rx code'),
        (12, 'bad', 'Mode'),
        (13, 'bad', 'Tuning step'),
    ],
)
def test_csv_rejects_invalid_field(index, value, message):
    """Translate malformed CSV fields into InvalidDataError."""
    values = Memory(number=1).to_csv()
    values[2] = '146.520000'
    values[index] = value

    with pytest.raises(InvalidDataError, match=message):
        Memory().really_from_csv(values)
