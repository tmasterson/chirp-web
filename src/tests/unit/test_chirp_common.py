"""Tests for the main shared radio abstractions."""

from chirp_web import chirp_common, errors

import pytest


class MemoryRadio(chirp_common.Radio):
    """Small radio implementation for static bank tests."""

    def __init__(self, bounds):
        super().__init__(None)
        self.features = chirp_common.RadioFeatures()
        self.features.memory_bounds = bounds

    def get_features(self):
        return self.features

    def get_memory(self, number):
        return chirp_common.Memory(number=number)


@pytest.mark.parametrize(
    ('frequency', 'formatted'),
    [
        (0, '0.000000'),
        (146520000, '146.520000'),
        (-1, '-0.000001'),
        (1234567890123456789, '1234567890123.456789'),
    ],
)
def test_frequency_formatting_is_exact_for_positive_and_negative_hz(
        frequency, formatted):
    """Format integral hertz without float precision loss."""
    assert chirp_common.format_freq(frequency) == formatted


def test_static_bank_model_partitions_uneven_ranges_without_losing_memories():
    """Partition an inclusive channel range evenly, including empty banks."""
    model = chirp_common.StaticBankModel(MemoryRadio((1, 11)), banks=3)
    banks = model.get_mappings()

    assert [[mem.number for mem in model.get_mapping_memories(bank)]
            for bank in banks] == [
        [1, 2, 3], [4, 5, 6, 7], [8, 9, 10, 11],
    ]
    assert model.get_memory_mappings(chirp_common.Memory(number=7)) == [
        banks[1],
    ]

    sparse = chirp_common.StaticBankModel(MemoryRadio((0, 1)), banks=4)
    assert [len(sparse.get_mapping_memories(bank))
            for bank in sparse.get_mappings()] == [0, 1, 0, 1]


@pytest.mark.parametrize('banks', [0, -1, 1.5, True])
def test_static_bank_model_rejects_invalid_bank_counts(banks):
    """Require a positive integer bank count."""
    with pytest.raises(ValueError, match='positive integer'):
        chirp_common.StaticBankModel(MemoryRadio((0, 9)), banks=banks)


def test_static_bank_model_rejects_unknown_banks_and_channels():
    """Report invalid bank and memory requests instead of indexing blindly."""
    model = chirp_common.StaticBankModel(MemoryRadio((0, 9)), banks=2)
    invalid_bank = chirp_common.MemoryMapping(model, 3, 'Invalid')

    with pytest.raises(ValueError, match='Unknown bank'):
        model.get_mapping_memories(invalid_bank)
    with pytest.raises(ValueError, match='outside bounds'):
        model.get_memory_mappings(chirp_common.Memory(number=10))


def test_required_step_handles_custom_steps_and_unsupported_frequencies():
    """Reuse standard tuning steps and accept additional allowed increments."""
    assert chirp_common.required_step(146520000) == 5.0
    assert chirp_common.required_step(146521000, allowed=[1.0]) == 1.0
    with pytest.raises(errors.InvalidDataError, match='Unable to find'):
        chirp_common.required_step(146520501, allowed=[])


def test_sanitize_string_preserves_unicode_and_reuses_character_rules():
    """Replace invalid ASCII characters while leaving Unicode intact."""
    assert chirp_common.sanitize_string(
        'AB\n☃', validcharset='AB', replacechar='?') == 'AB?☃'
    assert chirp_common.sanitize_string(
        'abc', validcharset='abc') == 'abc'


def test_version_comparison_uses_candidate_and_installed_versions(monkeypatch):
    """Compare the supplied candidate against the current package version."""
    import chirp_web.__version__ as version_module

    monkeypatch.setattr(version_module, 'version', '1.2.3')
    assert chirp_common.is_version_newer('1.2.4')
    assert not chirp_common.is_version_newer('1.2.3')
    assert not chirp_common.is_version_newer('1.2.2')
