"""Tests for common radio utilities."""

from chirp_web.utils.common import (
    ALL_DTCS_CODES,
    OLD_TONES,
    TONES,
    VALIDTONE,
    format_freq,
    parse_freq,
)

import pytest


@pytest.mark.parametrize(
    ('frequency', 'expected'),
    [
        ('', 0),
        ('  ', 0),
        ('146', 146000000),
        ('146.52', 146520000),
        ('146.520000', 146520000),
        ('.52', 520000),
        ('146.5 MHz', 146500000),
        ('450 kHz', 450000),
        (' 146.52 MHz ', 146520000),
    ],
)
def test_parse_freq(frequency, expected):
    """Parse common frequency representations to Hz."""
    assert parse_freq(frequency) == expected


@pytest.mark.parametrize(
    'frequency',
    ['invalid', '1.1234567', 'invalid MHz', '1.2.3'],
)
def test_parse_freq_rejects_invalid_input(frequency):
    """Invalid values and unsupported precision raise ValueError."""
    with pytest.raises(ValueError):
        parse_freq(frequency)


@pytest.mark.parametrize(
    ('frequency', 'expected'),
    [
        (0, '0.000000'),
        (146520000, '146.520000'),
        (1, '0.000001'),
        (-1, '-0.000001'),
        (1234567890123456789, '1234567890123.456789'),
    ],
)
def test_format_freq(frequency, expected):
    """Format integral Hz accurately as MHz with six decimal places."""
    assert format_freq(frequency) == expected


@pytest.mark.parametrize('tone', [67.0, 254.1, 50.1, 299.9])
def test_validtone_accepts_float_in_range(tone):
    """Recognize floating point tones strictly inside the valid range."""
    assert VALIDTONE(tone)


@pytest.mark.parametrize('tone', [50.0, 300.0, 49.9, 300.1, 67, '67.0'])
def test_validtone_rejects_out_of_range_or_non_float(tone):
    """Reject boundary values, out-of-range values, and non-floats."""
    assert not VALIDTONE(tone)


def test_common_tone_and_dtcs_constants():
    """Keep legacy tone ordering and enumerate all DTCS digit combinations."""
    assert OLD_TONES == tuple(tone for tone in TONES if tone not in {
        159.8, 165.5, 171.3, 177.3, 183.5, 189.9, 196.6, 199.5, 206.5,
        229.1, 254.1,
    })
    assert len(ALL_DTCS_CODES) == 512
    assert ALL_DTCS_CODES[0] == 0
    assert ALL_DTCS_CODES[-1] == 777
