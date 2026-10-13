"""Tests for radio settings values, groups, and memory mapping."""

from types import SimpleNamespace

from chirp_web.settings import (
    InvalidNameError,
    InvalidValueError,
    MemSetting,
    RadioSetting,
    RadioSettingGroup,
    RadioSettingValueBoolean,
    RadioSettingValueInteger,
    RadioSettingValueInvertedBoolean,
    RadioSettings,
)

import pytest


def test_integer_value_boundaries_and_validation():
    """Accept both endpoints and reject values outside the setting range."""
    value = RadioSettingValueInteger(1, 10, 1)
    value.initialize()
    value.set_value(10)

    assert int(value) == 10
    assert value.changed()
    with pytest.raises(InvalidValueError, match='not in range'):
        value.set_value(11)
    with pytest.raises(InvalidValueError, match='integer is required'):
        value.set_value('invalid')


def test_setting_groups_preserve_insertion_order_and_walk_nested_values():
    """Iterate settings in insertion order and recursively walk subgroups."""
    first = RadioSetting('first', 'First', RadioSettingValueInteger(0, 5, 1))
    second = RadioSetting('second', 'Second',
                          RadioSettingValueInteger(0, 5, 2))
    subgroup = RadioSettingGroup('nested', 'Nested', second)
    group = RadioSettingGroup('root', 'Root', first, subgroup)

    assert list(group) == [first, subgroup]
    assert list(group.walk()) == [first, second]
    assert 'first' in str(group)
    assert list(RadioSettings(group).walk()) == [first, second]


def test_settings_reject_invalid_names_values_and_frozen_changes():
    """Reject malformed settings and writes to frozen groups or values."""
    with pytest.raises(InvalidNameError):
        RadioSettingGroup('bad%name', 'Bad')

    value = RadioSettingValueInteger(0, 1, 0)
    value.initialize()
    value.set_mutable(False)
    with pytest.raises(InvalidValueError, match='not mutable'):
        value.set_value(1)

    group = RadioSettingGroup('root', 'Root')
    group.set_frozen()
    with pytest.raises(ValueError, match='frozen'):
        group.append(RadioSettingGroup('child', 'Child'))


def test_memsetting_applies_nested_and_inverted_boolean_values():
    """Resolve dotted paths and encode inverted booleans for memory objects."""
    nested = SimpleNamespace(enabled=False)
    root = SimpleNamespace(settings=SimpleNamespace(items=[None, nested]))
    setting = MemSetting(
        'settings.items[1].enabled', 'Enabled',
        RadioSettingValueInvertedBoolean(True, mem_vals=(0, 1)))

    setting.apply_to_memobj(root)

    assert nested.enabled == 0


def test_boolean_memsetting_maps_regular_boolean_values():
    """Encode regular booleans through their configured memory values."""
    target = SimpleNamespace(enabled=None)
    setting = MemSetting(
        'enabled', 'Enabled', RadioSettingValueBoolean(True, mem_vals=(2, 4)))

    setting.apply_to_memobj(target)

    assert target.enabled == 4
