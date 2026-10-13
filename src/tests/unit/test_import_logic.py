"""Tests for copying memories between radios."""

from chirp_web import chirp_common, errors, import_logic

import pytest


class FakeRadio(chirp_common.Radio):
    """Radio stub for memory-import tests."""

    def __init__(self, features=None):
        super().__init__(None)
        self.features = features or chirp_common.RadioFeatures()
        self.features.valid_bands = [(100000000, 200000000)]
        self.features.memory_bounds = (0, 20)
        self.current = chirp_common.Memory(number=1)

    def get_features(self):
        return self.features

    def get_memory(self, number):
        return self.current

    def set_memory(self, memory):
        self.current = memory


def test_import_memory_copies_and_applies_overrides_without_mutating_source():
    """Copy a compatible memory, filter its name, and apply overrides."""
    radio = FakeRadio()
    source = chirp_common.Memory(number=1, name='source')
    source.freq = 146520000

    imported = import_logic.import_mem(
        radio, chirp_common.RadioFeatures(), source,
        overrides={'name': 'custom'})

    assert imported is not source
    assert imported.name == 'CUSTOM'
    assert imported.freq == source.freq
    assert source.name == 'source'
    assert imported.immutable == []


def test_import_memory_rejects_frequency_outside_destination_bands():
    """Reject a memory whose receive frequency is unsupported."""
    source = chirp_common.Memory(number=1)
    source.freq = 220000000

    with pytest.raises(import_logic.DestNotCompatible,
                       match='out of supported range'):
        import_logic.import_mem(FakeRadio(), None, source)


def test_find_closest_power_preserves_first_level_on_ties():
    """Choose the closest destination power, with stable tie handling."""
    low = chirp_common.PowerLevel('Low', watts=1)
    high = chirp_common.PowerLevel('High', watts=2)

    assert import_logic.find_closest_power(1.5, [low, high]) is low


def test_ensure_has_calls_fills_available_slots_and_reports_full_lists():
    """Add missing D-STAR calls, or fail clearly when a list is full."""
    class DstarRadio:
        def __init__(self, urcalls, rptcalls):
            self.urcalls = urcalls
            self.rptcalls = rptcalls

        def get_urcall_list(self):
            return self.urcalls

        def get_repeater_call_list(self):
            return self.rptcalls

        def set_urcall_list(self, calls):
            self.urcalls = calls

        def set_repeater_call_list(self, calls):
            self.rptcalls = calls

    memory = chirp_common.DVMemory()
    memory.dv_urcall = 'CQCQCQ'
    memory.dv_rpt1call = 'RPT1'
    memory.dv_rpt2call = 'RPT2'
    radio = DstarRadio([''], ['', ''])

    import_logic.ensure_has_calls(radio, memory)

    assert radio.urcalls == ['CQCQCQ']
    assert set(radio.rptcalls) == {'RPT1', 'RPT2'}

    full = DstarRadio(['USED'], ['', ''])
    with pytest.raises(errors.RadioError, match='No room to add callsign'):
        import_logic.ensure_has_calls(full, memory)
