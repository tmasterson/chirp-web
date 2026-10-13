"""Tests for powerlevels."""

import math

from chirp_web.utils.powerlevel import (
        PowerLevel,
)

import pytest


def calc_dbm(x):
    """Calculate dbm for a given number (watts)."""
    return 10*math.log10(x)+30


def calc_watts(x):
    """Calculate watts from a given number normally dbm."""
    return round(math.pow(10, x/10)/1000, 1)


def test_create_with_no_power():
    """Test creating an instance with no power parameters."""
    t = PowerLevel('test')
    assert t._label == 'test'
    assert t._power == 0


def test_create_with_wats():
    """Test creation given wats as a parameter."""
    t = PowerLevel('test', watts=25)
    dbm = calc_dbm(25)
    assert t._label == 'test' and t._power == dbm


def test_create_with_dbm():
    """Test creation with a dbm parameter>."""
    t = PowerLevel('test', dbm=50)
    assert t._label == 'test' and t._power == 50.0


def test_create_with_wats_dbm():
    """Test creation with all parameters watts have precedenc over dbm."""
    t = PowerLevel('test', watts=50, dbm=25)
    dbm = calc_dbm(50)
    assert t._label == 'test' and t._power == dbm


def test_watts_to_dbm():
    """Test conversion of watts to dbm."""
    t1 = PowerLevel('test')
    dbm = calc_dbm(20.0)
    assert t1.watts_to_dbm(20.0) == dbm


def test_dbm_to_watts():
    """Test conversion of dbm to watts."""
    t1 = PowerLevel('test')
    watts = calc_watts(25.775)
    assert t1.dbm_to_watts(25.775) == watts


def test_PowerLevel_str():
    """Test conversion to string."""
    t = PowerLevel('test')
    assert str(t) == 'test'


def test_to_int():
    """Test int conversion of power level."""
    t = PowerLevel('test', dbm=15.7)
    assert int(t) == 15


def test_to_float():
    """Test the float function of pwer level."""
    t = PowerLevel('test', watts=15)
    dbm = calc_dbm(15)
    assert float(t) == dbm


def test_subtraction():
    """Test subtracting one power level from another."""
    t1 = PowerLevel('test', dbm=30)
    t2 = PowerLevel('test', dbm=10)
    assert t1-t2 == 20


def test_addition():
    """Test addition of power levels."""
    t1 = PowerLevel('test', dbm=15)
    t2 = PowerLevel('test', dbm=20)
    assert t1+t2 == 35


def test_equality():
    """Test to see if 2 power levels are equal."""
    t1 = PowerLevel('test', watts=15)
    t2 = PowerLevel('test2', watts=15)
    assert t1 == t2


def test_less_than():
    """Test that one power level is less than anouther."""
    t1 = PowerLevel('test', watts=15)
    t2 = PowerLevel('test2', watts=10)
    assert t2 < t1


def test_greater_than():
    """Test that one power level is greater than another."""
    t1 = PowerLevel('test', watts=15)
    t2 = PowerLevel('test2', watts=10)
    assert t1 > t2


def test_bool():
    """Test bollean function of powerlevel."""
    t1 = PowerLevel('test', dbm=10)
    assert t1


def test_repr():
    """Test repr function."""
    t1 = PowerLevel('test', dbm=15.6)
    assert repr(t1) == 'test (15 dbm)'


def test_parse_power_with_valid_input():
    """Test parse_power function."""
    t1 = PowerLevel.parse_power('9W')
    dbm1 = calc_dbm(9.0)
    assert t1._label == '9.0W'
    assert t1._power == dbm1
    t2 = PowerLevel.parse_power('15')
    dbm2 = calc_dbm(15)
    assert t2._label == '15W'
    assert t2._power == dbm2


def test_parse_power_with_bad_string():
    """Test if we get a ValueError given a test string."""
    with pytest.raises(ValueError):
        PowerLevel.parse_power('test')


def test_parse_power_invalid_input():
    """Test that we get a ValueError when string has something other than W."""
    with pytest.raises(ValueError):
        PowerLevel.parse_power('9.0S')


@pytest.mark.parametrize(
    ('text', 'label'),
    [
        (' 9w ', '9.0W'),
        ('12.5 W', '12W'),
        ('.5W', '0.5W'),
        ('0W', '0.0W'),
    ],
)
def test_parse_power_spacing_units_and_boundaries(text, label):
    """Accept supported unit spelling, surrounding whitespace, and zero."""
    assert str(PowerLevel.parse_power(text)) == label


@pytest.mark.parametrize('text', ['', 'W', '-1W', '1.2.3W', '2 kW'])
def test_parse_power_rejects_malformed_or_unsupported_units(text):
    """Reject blank, negative, malformed, and unknown-unit specifications."""
    with pytest.raises(ValueError):
        PowerLevel.parse_power(text)


def test_power_level_comparison_with_other_types():
    """Return normal rich-comparison results for non-power operands."""
    power = PowerLevel('test', dbm=10)

    assert power != object()
    with pytest.raises(TypeError):
        _ = power < object()
