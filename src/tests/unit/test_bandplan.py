"""Tests for band definitions and plan selection."""

from types import SimpleNamespace

from chirp_web import bandplan
from chirp_web.chirp_common import MODES, TUNING_STEPS

import pytest


class Config:
    """Minimal band-plan configuration stub."""

    def __init__(self, enabled=None):
        self.enabled = enabled or {}

    def get_bool(self, name, section):
        return self.enabled.get(name, False)


def test_band_comparison_containment_and_inverse():
    """Compare band limits and invert the RX/TX range and offset."""
    original = bandplan.Band(
        (100, 200), 'Example meter band', mode=MODES[0],
        step_khz=TUNING_STEPS[0], input_offset=10)
    inverse = original.inverse()

    assert original.contains(bandplan.Band((120, 180), 'Contained'))
    assert original.width() == 100
    assert original == bandplan.Band((100, 200), 'Same limits')
    assert original != object()
    assert inverse.limits == (110, 210)
    assert inverse.offset == -10
    assert inverse.duplex == '-'


@pytest.mark.parametrize(
    'kwargs',
    [
        {'limits': (200, 100)},
        {'mode': 'invalid'},
        {'step_khz': -1},
        {'tones': [999.0]},
    ],
)
def test_band_rejects_invalid_settings(kwargs):
    """Reject invalid frequency ranges and unsupported radio settings."""
    values = {'limits': (100, 200), 'name': 'Invalid'}
    values.update(kwargs)

    with pytest.raises(ValueError):
        bandplan.Band(**values)


def test_band_plans_combine_matching_defaults_in_specificity_order():
    """Use plan defaults and retain properties omitted by a narrower band."""
    broad = bandplan.Band(
        (100, 300), 'Broad', mode='FM', step_khz=5.0, input_offset=10)
    narrow = bandplan.Band((150, 200), 'Narrow', tones=(88.5,))
    plan = SimpleNamespace(bands=[broad, narrow])
    plans = bandplan.BandPlans.__new__(bandplan.BandPlans)
    plans._config = Config({'example': True})
    plans.plans = {'example': ('Example', plan)}

    result = plans.get_defaults_for_frequency(175)

    assert result.mode == 'FM'
    assert result.step_khz == 5.0
    assert result.offset == 10
    assert result.tones == (88.5,)
    assert result.name == '175/Broad/Narrow'


def test_repeater_bands_without_enabled_plan_is_empty():
    """Handle a configuration with no enabled band plan."""
    plans = bandplan.BandPlans.__new__(bandplan.BandPlans)
    plans._config = Config()
    plans.plans = {}

    assert plans.get_repeater_bands() == []
