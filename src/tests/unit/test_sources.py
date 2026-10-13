"""Tests for network-backed radio sources using local response fixtures."""

import importlib
import json
from types import SimpleNamespace

from chirpQt import chirp_common

import pytest

import requests

base = importlib.import_module('chirpQt.sources.base')
dmrmarc = importlib.import_module('chirpQt.sources.dmrmarc')
przemienniki_eu = importlib.import_module('chirpQt.sources.przemienniki_eu')
przemienniki_net = importlib.import_module('chirpQt.sources.przemienniki_net')
radioreference = importlib.import_module('chirpQt.sources.radioreference')
repeaterbook = importlib.import_module('chirpQt.sources.repeaterbook')


class FakeStatus:
    """Capture the observable status reporting from a source query."""

    def __init__(self):
        """Initialize an empty status record."""
        self.updates = []
        self.failures = []
        self.ended = False

    def send_status(self, message, percent):
        """Record a progress update."""
        self.updates.append((message, percent))

    def send_fail(self, reason):
        """Record a failed query."""
        self.failures.append(reason)

    def send_end(self):
        """Record successful completion."""
        self.ended = True


class FakeCSV:
    """Provide controlled CSV memories while counting lookups."""

    def __init__(self, memories):
        """Initialize the memory map used by the fake CSV driver."""
        self.memories = memories
        self.calls = []

    def _load(self, rows):
        """Consume the input rows like the real CSV loader."""
        self.rows = list(rows)

    def get_memory(self, number):
        """Return a mapped memory or an empty slot."""
        self.calls.append(number)
        return self.memories.get(
            number, SimpleNamespace(empty=True, name='', number=number))


class FakeResponse:
    """Minimal requests response double for streamed and JSON payloads."""

    def __init__(self, payload=b'', status_code=200, reason='OK'):
        """Initialize a byte payload and HTTP response metadata."""
        self.payload = payload
        self.status_code = status_code
        self.reason = reason
        self.url = 'https://example.test/'

    def raise_for_status(self):
        """Raise the HTTP error for unsuccessful response codes."""
        if self.status_code >= 400:
            raise requests.HTTPError(self.reason)

    def iter_lines(self):
        """Yield response lines."""
        return self.payload.splitlines()

    def iter_content(self, chunk_size):
        """Yield response chunks of the requested size."""
        for index in range(0, len(self.payload), chunk_size):
            yield self.payload[index:index + chunk_size]

    def json(self):
        """Decode the payload as JSON."""
        return json.loads(self.payload)


def test_network_result_radio_is_immutable_and_reports_memory_bounds():
    """Expose empty bounds and reject edits on network-backed memories."""
    radio = base.NetworkResultRadio()
    assert radio.get_features().memory_bounds == (0, -1)
    assert radio.validate_memory(chirp_common.Memory()) == [
        'Network source is immutable']
    with pytest.raises(Exception, match='Network source is immutable'):
        radio.set_memory(chirp_common.Memory())


@pytest.mark.parametrize(
    ('value', 'expected'),
    [
        ('D023', ('DTCS', 23)),
        ('88.5', ('Tone', 88.5)),
        ('CSQ', (None, None)),
        ('Restricted', (None, None)),
        ('', (None, None)),
        ('unsupported', (None, None)),
    ],
)
def test_repeaterbook_parse_tone_formats(value, expected):
    """Parse supported PL values and treat unknown formats as no tone."""
    assert repeaterbook.parse_tone(value) == expected


def test_repeaterbook_distance_handles_known_geographic_distance():
    """Calculate the approximate distance between nearby coordinates."""
    assert repeaterbook.distance(0, 0, 0, 1) == pytest.approx(111.19, rel=0.01)


@pytest.mark.parametrize('source_module, radio_type', [
    (przemienniki_eu, przemienniki_eu.PrzemiennikiEu),
    (przemienniki_net, przemienniki_net.PrzemiennikiNet),
])
def test_przemienniki_fetch_loads_each_csv_memory_once(
        monkeypatch, source_module, radio_type):
    """Avoid fetching each CSV slot twice and preserve caller parameters."""
    first_number = 0 if radio_type is przemienniki_eu.PrzemiennikiEu else 1
    memories = {
        first_number: SimpleNamespace(empty=False, name='Zulu', number=91),
        first_number + 1: SimpleNamespace(
            empty=False, name='Alpha', number=92),
    }
    csv = FakeCSV(memories)
    monkeypatch.setattr(source_module.generic_csv, 'CSVRadio',
                        lambda _filename: csv)
    monkeypatch.setattr(source_module.requests, 'get',
                        lambda *args, **kwargs: FakeResponse(b'header\\n'))
    radio = radio_type()
    status = FakeStatus()
    params = ({'range': '0'} if radio_type is przemienniki_net.PrzemiennikiNet
              else {})
    original_params = params.copy()

    radio.do_fetch(status, params)

    assert [memory.name for memory in radio._memories] == ['Alpha', 'Zulu']
    assert [memory.number for memory in radio._memories] == [1, 2]
    assert len(csv.calls) == len(set(csv.calls))
    assert params == original_params
    assert status.ended


def test_przemienniki_network_failure_is_reported(monkeypatch):
    """Report a connection error without marking the query successful."""
    def fail_request(*args, **kwargs):
        raise requests.ConnectionError('offline')

    monkeypatch.setattr(przemienniki_eu.requests, 'get', fail_request)
    status = FakeStatus()

    przemienniki_eu.PrzemiennikiEu().do_fetch(status, {})

    assert status.failures == ['Unable to query']
    assert not status.ended


def test_przemienniki_net_missing_range_and_coordinates_are_supported(
        monkeypatch):
    """Allow optional query parameters to be omitted."""
    csv = FakeCSV({})
    monkeypatch.setattr(przemienniki_net.generic_csv, 'CSVRadio',
                        lambda _filename: csv)
    captured = {}

    def get(*args, **kwargs):
        captured.update(kwargs)
        return FakeResponse(b'header\\n')

    monkeypatch.setattr(przemienniki_net.requests, 'get', get)
    status = FakeStatus()
    przemienniki_net.PrzemiennikiNet().do_fetch(status, {})

    assert 'range' not in captured['params']
    assert status.ended


def test_dmrmarc_fetch_converts_results_and_handles_http_error(monkeypatch):
    """Convert a valid repeater and surface network request failures."""
    response = FakeResponse(json.dumps({'results': [{
        'city': 'Town', 'frequency': '146.520', 'offset': '0.600',
        'color_code': '3', 'details': 'Local repeater',
    }]}).encode())
    monkeypatch.setattr(dmrmarc.requests, 'get', lambda *args, **kwargs:
                        response)
    radio = dmrmarc.DMRMARCRadio()
    status = FakeStatus()

    radio.do_fetch(status, {'city': '', 'state': '', 'country': ''})

    assert radio.get_memory(0).name == 'Town'
    assert radio.get_memory(0).mode == 'DMR'
    assert status.ended

    def fail_request(*args, **kwargs):
        raise requests.ConnectionError('offline')

    monkeypatch.setattr(dmrmarc.requests, 'get', fail_request)
    failed = FakeStatus()
    dmrmarc.DMRMARCRadio().do_fetch(
        failed, {'city': '', 'state': '', 'country': ''})
    assert failed.failures == ['Unable to query DMR-MARC']


def test_dmrmarc_malformed_response_reports_parse_failure(monkeypatch):
    """Return a failure status when the API omits its results field."""
    monkeypatch.setattr(dmrmarc.requests, 'get',
                        lambda *args, **kwargs: FakeResponse(b'{}'))
    status = FakeStatus()

    dmrmarc.DMRMARCRadio().do_fetch(
        status, {'city': '', 'state': '', 'country': ''})

    assert status.failures == ['Unable to parse DMR-MARC response']


def _repeater(**overrides):
    """Build a valid RepeaterBook result with selected overrides."""
    item = {
        'D-Star': 'No', 'Callsign': 'K0ABC', 'Frequency': '146.520',
        'Input Freq': '146. -', 'PL': '88.5', 'TSQ': '', 'DMR': 'No',
        'System Fusion': 'No', 'FM Analog': 'Yes', 'Rptr ID': '1',
        'State': 'State', 'County': 'County', 'Nearest City': 'Town',
        'Use': 'OPEN', 'Notes': '', 'Landmark': 'Repeater',
        'Operational Status': 'On-air', 'Lat': '1', 'Long': '1',
    }
    item['Input Freq'] = '0'
    item.update(overrides)
    return item


def test_repeaterbook_fetch_filters_sorts_and_does_not_mutate_params(
        monkeypatch, tmp_path):
    """Apply proximity and text filters without consuming caller parameters."""
    data_file = tmp_path / 'repeaters.json'
    data_file.write_text(json.dumps({'count': 2, 'results': [
        _repeater(**{'Rptr ID': 'far', 'Lat': '10', 'Long': '10'}),
        _repeater(**{'Rptr ID': 'near', 'Landmark': 'Near',
                     'Lat': '1.1', 'Long': '1.1'}),
    ]}))
    radio = repeaterbook.RepeaterBook()
    monkeypatch.setattr(radio, 'get_data', lambda *args: str(data_file))
    params = {
        'country': 'United States', 'state': 'Any', 'service': 'gmrs',
        'lat': '1', 'lon': '1', 'dist': '100', 'filter': 'near',
        'bands': [], 'modes': [], 'fmconv': False, 'openonly': True,
        'cached': False,
    }
    original = params.copy()
    status = FakeStatus()

    radio.do_fetch(status, params)

    assert [memory.name for memory in radio._memories] == ['Near']
    assert radio._memories[0].number == 0
    assert params == original
    assert status.ended


def test_repeaterbook_empty_results_and_download(monkeypatch, tmp_path):
    """Report empty data and successfully cache a downloaded JSON response."""
    data_file = tmp_path / 'repeaters.json'
    data_file.write_text(json.dumps({'count': 0, 'results': []}))
    radio = repeaterbook.RepeaterBook()
    monkeypatch.setattr(radio, 'get_data', lambda *args: str(data_file))
    status = FakeStatus()

    radio.do_fetch(status, {'country': 'US', 'state': 'Any'})

    assert status.failures == ['No results!']
    assert not radio._memories

    monkeypatch.setattr(
        repeaterbook.chirp_platform, 'get_platform',
        lambda: SimpleNamespace(config_file=lambda _name: str(tmp_path)))
    monkeypatch.setattr(repeaterbook.os.path, 'getmtime',
                        lambda _filename: 0)
    monkeypatch.setattr(repeaterbook.requests, 'get',
                        lambda *args, **kwargs: FakeResponse(
                            b'{"count": 1, "results": []}'))
    status = FakeStatus()

    downloaded = repeaterbook.RepeaterBook().get_data(
        status, 'United States', 'Test', 'gmrs')

    assert downloaded is not None
    with open(downloaded, 'rb') as data_stream:
        assert json.load(data_stream)['count'] == 1
    assert not status.failures


def test_repeaterbook_invalid_download_is_reported_and_cleaned(
        monkeypatch, tmp_path):
    """Remove a malformed response's temporary cache file."""
    monkeypatch.setattr(
        repeaterbook.chirp_platform, 'get_platform',
        lambda: SimpleNamespace(config_file=lambda _name: str(tmp_path)))
    monkeypatch.setattr(repeaterbook.os.path, 'getmtime',
                        lambda _filename: 0)
    monkeypatch.setattr(repeaterbook.requests, 'get',
                        lambda *args, **kwargs: FakeResponse(b'not json'))
    status = FakeStatus()

    result = repeaterbook.RepeaterBook().get_data(
        status, 'United States', 'Test', 'gmrs')

    assert result is None
    assert status.failures == ['RepeaterBook returned invalid response']
    assert not list(tmp_path.glob('*.tmp'))


def test_radioreference_fetch_uses_extend_and_handles_empty_categories(
        monkeypatch):
    """Complete an empty Canadian query without division-by-zero failures."""
    class Service:
        def getCountyInfo(self, county_id, auth):
            return SimpleNamespace(cats=[], agencyList=[])

    class Client:
        service = Service()

    radio = radioreference.RadioReferenceRadio.__new__(
        radioreference.RadioReferenceRadio)
    radio._client = Client()
    radio._auth = {}
    radio._freqs = []
    status = FakeStatus()

    radio.do_fetch(status, {'country': 'CA', 'zipcounty': '1'})

    assert radio._freqs == []
    assert status.ended


def test_radioreference_fetch_collects_category_frequencies():
    """Append category frequencies and report successful completion."""
    frequency = SimpleNamespace()
    subcategory = SimpleNamespace(scid=7, scName='Local')
    category = SimpleNamespace(cName='Public Safety', subcats=[subcategory])

    class Service:
        def getCountyInfo(self, county_id, auth):
            return SimpleNamespace(cats=[category], agencyList=[])

        def getSubcatFreqs(self, subcat_id, auth):
            assert subcat_id == 7
            return [frequency]

    class Client:
        service = Service()

    radio = radioreference.RadioReferenceRadio.__new__(
        radioreference.RadioReferenceRadio)
    radio._client = Client()
    radio._auth = {}
    radio._freqs = []
    status = FakeStatus()

    radio.do_fetch(status, {'country': 'CA', 'zipcounty': '1'})

    assert radio._freqs == [frequency]
    assert status.ended
