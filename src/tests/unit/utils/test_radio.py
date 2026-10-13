"""Tests for the radio abstractions."""

from chirp_web.errors import ImmutableValueError
from chirp_web.utils.memory import Memory
from chirp_web.utils.radio import Radio, RadioFeatures

import pytest


def test_radio_features_defaults_and_docs():
    """Expose initialized feature values and their documentation."""
    features = RadioFeatures()

    assert features.has_dtcs is True
    assert features.valid_modes
    assert features.memory_bounds == (0, 1)
    assert 'DTCS' in features.get_doc('has_dtcs')
    assert features.is_a_feature('has_dtcs')
    assert not features.is_a_feature('unknown')
    assert features['has_dtcs'] is True


@pytest.mark.parametrize(
    ('name', 'value'),
    [
        ('has_dtcs', 'yes'),
        ('valid_tuning_steps', [0, 5]),
        ('valid_tones', [50.0]),
        ('valid_name_length', -1),
        ('memory_bounds', (0, 1, 2)),
    ],
)
def test_radio_features_reject_invalid_values(name, value):
    """Reject values that violate a feature's validator."""
    with pytest.raises(ValueError):
        setattr(RadioFeatures(), name, value)


def test_radio_features_reject_unknown_attributes():
    """Reject unregistered feature names."""
    with pytest.raises(ValueError, match='No such attribute'):
        RadioFeatures().unknown_feature = True


class MemorySinkRadio(Radio):
    """Minimal radio that records calls to set_memory."""

    def set_memory(self, memory):
        """Save and set memory value."""
        self.saved_memory = memory


def test_radio_defaults_format_name_and_pipe():
    """Provide sensible base behavior for an otherwise generic radio."""
    class TestRadio(MemorySinkRadio):
        VENDOR = 'Example'
        MODEL = 'Handheld'
        FORMATS = ['img']

    radio = TestRadio('pipe')
    assert radio.pipe == 'pipe'
    assert radio.errors == []
    assert radio.get_name() == 'Example Handheld'
    assert radio.supports_format('img')
    assert not radio.supports_format('csv')

    radio.set_pipe('new pipe')
    assert radio.pipe == 'new pipe'


def test_radio_erase_memory_supports_integer_and_extended_locations():
    """Erase both ordinary and named channels through set_memory."""
    radio = MemorySinkRadio(None)

    radio.erase_memory(7)
    assert radio.saved_memory.number == 7
    assert radio.saved_memory.empty
    assert radio.saved_memory.extd_number == ''

    radio.erase_memory('CALL')
    assert radio.saved_memory.extd_number == 'CALL'
    assert radio.saved_memory.empty


def test_radio_filter_name_respects_character_set_and_length():
    """Uppercase, filter, and truncate names according to radio features."""
    radio = MemorySinkRadio(None)

    assert radio.filter_name('ab!cdefg') == 'ABCDE'

    features = radio.get_features()
    features.valid_characters = 'abc '
    features.valid_name_length = 4
    radio.get_features = lambda: features
    assert radio.filter_name('a bcX') == 'a bc'


def test_radio_immutable_memory_policy():
    """Reject changes to immutable fields but allow equal values."""
    radio = MemorySinkRadio(None)
    original = Memory(name='fixed')
    original.immutable = ['name']
    unchanged = original.dupe()

    assert radio.check_set_memory_immutable_policy(original, unchanged) is None

    changed = original.dupe()
    changed.name = 'changed'
    with pytest.raises(ImmutableValueError, match='name'):
        radio.check_set_memory_immutable_policy(original, changed)
