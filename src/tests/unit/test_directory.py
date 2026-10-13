"""Tests for driver and file-format registration."""

from chirp_web import directory

import pytest


def _reset_registry(monkeypatch):
    """Give each test isolated driver and format registries."""
    monkeypatch.setattr(directory, 'DRV_TO_RADIO', {})
    monkeypatch.setattr(directory, 'RADIO_TO_DRV', {})
    monkeypatch.setattr(directory, 'AUX_FORMATS', set())
    monkeypatch.setattr(directory, 'ALLOW_DUPS', False)


def test_register_and_lookup_driver(monkeypatch):
    """Register a radio and look it up using either registry direction."""
    _reset_registry(monkeypatch)

    class ExampleRadio:
        VENDOR = 'Example/Radio'
        MODEL = 'Model (One)'
        VARIANT = 'V1'

    assert directory.radio_class_id(ExampleRadio) == (
        'Example_Radio_Model_One_V1')
    assert directory.register(ExampleRadio) is ExampleRadio
    assert directory.get_radio('Example_Radio_Model_One_V1') is ExampleRadio
    assert directory.get_driver(ExampleRadio) == 'Example_Radio_Model_One_V1'


def test_register_rejects_duplicate_driver_id(monkeypatch):
    """Reject conflicting models unless re-registration was enabled."""
    _reset_registry(monkeypatch)

    class FirstRadio:
        VENDOR = 'Example'
        MODEL = 'Radio'
        VARIANT = ''

    class ReplacementRadio:
        VENDOR = 'Example'
        MODEL = 'Radio'
        VARIANT = ''

    directory.register(FirstRadio)
    with pytest.raises(Exception, match='Duplicate radio driver id'):
        directory.register(ReplacementRadio)

    monkeypatch.setattr(directory, 'ALLOW_DUPS', True)
    directory.register(ReplacementRadio)
    assert directory.get_radio('Example_Radio') is ReplacementRadio
    assert FirstRadio not in directory.RADIO_TO_DRV
    assert directory.get_driver(ReplacementRadio) == 'Example_Radio'


def test_register_format_allows_same_pair_and_rejects_name_conflicts(
        monkeypatch):
    """Allow idempotent format registration but reserve each format name."""
    _reset_registry(monkeypatch)

    assert directory.register_format('CSV', '*.csv') == 'CSV'
    assert directory.register_format('CSV', '*.csv') == 'CSV'
    with pytest.raises(Exception, match='Duplicate format name'):
        directory.register_format('CSV', '*.txt')


def test_unknown_driver_lookup_is_reported():
    """Report an unknown driver with the requested key in the message."""
    with pytest.raises(Exception, match='Unknown radio type'):
        directory.get_radio('missing')
