"""Hardware-independent tests for the local web interface."""

import base64
import csv
import io
import time
from pathlib import Path
from types import SimpleNamespace

from chirp_web import chirp_common, settings
from chirp_web.drivers.fake import FakeLiveRadio
from chirp_web.sources import mapy73pl, satellites
from chirp_web.webui import api as web_api
from chirp_web.webui import service
from chirp_web.webui.api import create_app

from fastapi.testclient import TestClient

import pytest


@pytest.fixture
def client():
    """Provide an isolated local API app for each test."""
    with TestClient(
            create_app(), base_url='http://127.0.0.1:8765') as test_client:
        yield test_client


def csv_image():
    """Return a small valid CSV image accepted by the generic driver."""
    memory = chirp_common.Memory(0)
    memory.name = 'TEST'
    memory.freq = 146520000
    header = [field for field in chirp_common.Memory.CSV_FORMAT
              if field != 'Power']
    values = [value for field, value in zip(
            chirp_common.Memory.CSV_FORMAT, memory.to_csv())
              if field != 'Power']
    content = ','.join(header) + '\n' + ','.join(values) + '\n'
    return base64.b64encode(content.encode('utf-8')).decode('ascii')


def csv_image_with_memories(memories):
    """Return a CSV image containing the supplied memories."""
    output = io.StringIO()
    writer = csv.writer(output)
    fields = [field for field in chirp_common.Memory.CSV_FORMAT
              if field != 'Power']
    writer.writerow(fields)
    for memory in memories:
        writer.writerow([
            value for field, value in zip(
                chirp_common.Memory.CSV_FORMAT, memory.to_csv())
            if field != 'Power'
        ])
    return base64.b64encode(output.getvalue().encode()).decode('ascii')


class SimpleBankModel(chirp_common.BankModel):
    """A simple editable bank model for testing web bank support."""

    def __init__(self, radio):
        super().__init__(radio, name='Test banks')
        self._banks = [
            chirp_common.MemoryMapping(self, 0, 'Bank 1'),
            chirp_common.MemoryMapping(self, 1, 'Bank 2'),
        ]
        self._members = {bank.get_index(): [] for bank in self._banks}

    def get_num_mappings(self):
        return len(self._banks)

    def get_mappings(self):
        return list(self._banks)

    def add_memory_to_mapping(self, memory, mapping):
        members = self._members.setdefault(mapping.get_index(), [])
        if memory.number not in members:
            members.append(memory.number)

    def remove_memory_from_mapping(self, memory, mapping):
        self._members.setdefault(mapping.get_index(), [])
        self._members[mapping.get_index()] = [
            number for number in self._members[mapping.get_index()]
            if number != memory.number
        ]

    def get_mapping_memories(self, mapping):
        return [self._radio.get_memory(number)
                for number in self._members.get(mapping.get_index(), [])]

    def get_memory_mappings(self, memory):
        return [
            self._banks[index] for index, members in self._members.items()
            if memory.number in members
        ]


class BankedRadio(FakeLiveRadio):
    """Fake radio with an editable two-bank model."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self._bank_model = SimpleBankModel(self)
        for number in (1, 3, 5):
            self._bank_model.add_memory_to_mapping(self.get_memory(number),
                                                  self._bank_model.get_mappings()[0])

    def get_mapping_models(self):
        return [self._bank_model]


class NamedIndexedBankModel(SimpleBankModel,
                            chirp_common.MappingModelIndexInterface):
    """Bank model with the optional rename and ordering interfaces."""

    def __init__(self, radio):
        super().__init__(radio)
        self._banks = [
            chirp_common.NamedBank(self, 0, 'Bank 1'),
            chirp_common.NamedBank(self, 1, 'Bank 2'),
        ]
        self._positions = {number: number for number in (1, 3, 5)}
        for number in self._positions:
            self.add_memory_to_mapping(
                    radio.get_memory(number), self._banks[0])

    def get_index_bounds(self):
        return (0, 99)

    def get_memory_index(self, memory, mapping):
        return self._positions[memory.number]

    def set_memory_index(self, memory, mapping, index):
        self._positions[memory.number] = index


class NamedIndexedBankRadio(BankedRadio):
    """Fake radio exposing renameable banks and indexed membership."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._bank_model = NamedIndexedBankModel(self)


def test_home_and_loopback_request_guard(client):
    """Serve the home page but reject remote hosts and cross-origin callers."""
    home = client.get('/')
    assert home.status_code == 200
    assert 'CHIRP Web Web' in home.text
    sources = client.get('/api/sources')
    assert sources.status_code == 200
    assert {source['id'] for source in sources.json()} == {
        'dmrmarc', 'przemienniki-eu', 'przemienniki-net',
        'radioreference', 'repeaterbook', 'mapy73', 'amsat', 'satnogs',
    }
    repeaterbook = next(
        source for source in sources.json() if source['id'] == 'repeaterbook')
    assert any(field['name'] == 'bands' for field in repeaterbook['fields'])

    wrong_host = client.get('/', headers={'host': 'radio.example'})
    assert wrong_host.status_code == 403
    wrong_origin = client.get(
            '/', headers={'origin': 'https://radio.example'})
    assert wrong_origin.status_code == 403
    assert home.headers['X-Content-Type-Options'] == 'nosniff'


def test_open_edit_and_save_csv_image(client):
    """Open a file-backed channel list, edit it, and export the changes."""
    opened = client.post('/api/session/open', json={
        'filename': '../../channels.csv',
        'data_base64': csv_image(),
    })
    assert opened.status_code == 200
    assert opened.json()['name'] == 'Generic CSV'
    assert opened.json()['filename'] == 'channels.csv'
    assert opened.json()['supports_upload'] is False

    channels = client.get('/api/memories?start=0&limit=1')
    assert channels.status_code == 200
    assert channels.json()['memories'][0]['name'] == 'TEST'

    changed = client.patch('/api/memories/0', json={
        'name': 'REPEATER',
        'freq': 145500000,
    })
    assert changed.status_code == 200
    assert changed.json()['memory']['freq'] == 145500000
    assert client.get('/api/session').json()['dirty'] is True

    saved = client.post('/api/session/save')
    assert saved.status_code == 200
    csv_text = base64.b64decode(saved.json()['data_base64']).decode('utf-8')
    rows = list(csv.reader(io.StringIO(csv_text)))
    assert rows[0][0:3] == ['Location', 'Name', 'Frequency']
    assert rows[1][1] == 'REPEATER'
    assert rows[1][2] == '145.500000'
    assert client.get('/api/session').json()['dirty'] is False


def test_memory_change_can_be_undone_and_redone(client):
    """Keep one-step undo and redo history for memory edits."""
    assert client.post('/api/session/open', json={
        'filename': 'channels.csv', 'data_base64': csv_image(),
    }).status_code == 200
    assert client.patch('/api/memories/0', json={'name': 'UPDATED'}).status_code == 200
    assert client.get('/api/session/history').json() == {
        'can_undo': True, 'can_redo': False,
    }
    assert client.post('/api/session/undo').json() == {
        'can_undo': False, 'can_redo': True,
    }
    assert client.get('/api/memories?start=0&limit=1').json()[
        'memories'][0]['name'] == 'TEST'
    assert client.post('/api/session/redo').json() == {
        'can_undo': True, 'can_redo': False,
    }
    assert client.get('/api/memories?start=0&limit=1').json()[
        'memories'][0]['name'] == 'UPDATED'


def test_compare_image_and_copy_selected_channels(client):
    """Preview another image and copy selected memories without replacing it."""
    assert client.post('/api/session/open', json={
        'filename': 'channels.csv', 'data_base64': csv_image(),
    }).status_code == 200
    source_memory = chirp_common.Memory(0)
    source_memory.name = 'COPIED'
    source_memory.freq = 145500000
    compared = client.post('/api/session/compare', json={
        'filename': 'source.csv',
        'data_base64': csv_image_with_memories([source_memory]),
    })
    assert compared.status_code == 200
    assert compared.json()['memories'][0]['name'] == 'COPIED'
    copied = client.post('/api/sources/import', json={
        'query_id': compared.json()['query_id'], 'selected': [0],
    })
    assert copied.status_code == 200
    assert client.get('/api/memories?start=1&limit=1').json()[
        'memories'][0]['name'] == 'COPIED'


def test_bandplan_selection_and_frequency_defaults(client):
    """Expose plan selection and calculate desktop-compatible defaults."""
    plans = client.get('/api/bandplans')
    assert plans.status_code == 200
    assert 'north_america' in {plan['id'] for plan in plans.json()['plans']}
    selected = client.patch('/api/bandplans', json={'name': 'australia'})
    assert selected.status_code == 200
    assert selected.json()['selected'] == 'australia'
    defaults = client.post('/api/bandplans/defaults', json={
        'frequency': 146.52,
    })
    assert defaults.status_code == 200
    assert defaults.json()['name']
    assert defaults.json()['duplex'] in (None, '', '+', '-')


def test_power_and_extra_memory_fields_use_driver_validation(client):
    """Expose writable power levels and nested driver-specific fields."""
    class ExtraRadio(FakeLiveRadio):
        def get_features(self):
            features = super().get_features()
            features.has_variable_power = False
            features.valid_power_levels = [
                chirp_common.PowerLevel('Low', watts=5),
                chirp_common.PowerLevel('High', watts=10),
            ]
            return features

    radio = ExtraRadio(None)
    memory = radio.get_memory(1)
    memory.extra = settings.RadioSettingGroup(
            'extra', 'Extra',
            settings.RadioSetting(
                'squelch', 'Squelch',
                settings.RadioSettingValueInteger(0, 9, 3)))
    radio.set_memory(memory)
    client.app.state.session._replace_radio(radio, 'extra.img', None)

    listed = client.get('/api/memories?start=1&limit=1').json()['memories'][0]
    assert listed['power'] is None
    assert listed['extra'][0]['path'] == ['extra', 'squelch']
    high_power = client.get('/api/session').json()[
        'features']['valid_power_levels'][1]['value']
    changed = client.patch('/api/memories/1', json={
        'power': high_power,
        'extra_changes': [{
            'path': ['extra', 'squelch'], 'value': 7,
        }],
    })
    assert changed.status_code == 200
    assert changed.json()['memory']['power'] == high_power
    assert changed.json()['memory']['extra'][0]['value'] == 7
    invalid = client.patch('/api/memories/1', json={
        'power': 7,
    })
    assert invalid.status_code == 422


def test_banks_support_optional_rename_and_memory_index(client):
    """Allow renaming and ordering only when the radio model supports it."""
    radio = NamedIndexedBankRadio(None)
    client.app.state.session._replace_radio(radio, 'banks.img', None)
    renamed = client.patch('/api/banks', json={
        'model': 'Test banks', 'bank_index': 0, 'name': 'Local',
    })
    assert renamed.status_code == 200
    assert renamed.json()['mappings'][0]['name'] == 'Local'
    moved = client.patch('/api/banks', json={
        'model': 'Test banks', 'bank_index': 0,
        'memory_number': 1, 'index': 25,
    })
    assert moved.status_code == 200
    assert moved.json()['mappings'][0]['positions']['1'] == 25


def test_satellite_sources_use_mocked_public_apis(client, monkeypatch):
    """Convert AMSAT and SatNOGS responses without live network access."""
    class Response:
        def __init__(self, data):
            self.data = data

        def raise_for_status(self):
            return None

        def json(self):
            return self.data

    def get(url, **kwargs):
        if url == satellites.AMSAT_URL:
            return Response([{
                'name': 'TestSat', 'downlink': '145.850-145.950',
                'uplink': '435.250', 'mode': 'FM',
            }])
        if url == satellites.SATNOGS_SATELLITES_URL:
            return Response([{
                'sat_id': 1, 'name': 'Orbiter', 'norad_cat_id': 12345,
            }])
        if url == satellites.SATNOGS_TRANSMITTERS_URL:
            return Response([{
                'sat_id': 1, 'description': 'VHF', 'downlink_low': 145800000,
                'uplink_low': 435000000, 'mode': 'FMN',
            }])
        raise AssertionError(f'Unexpected URL: {url}')

    monkeypatch.setattr(satellites.requests, 'get', get)
    amsat = client.post('/api/sources/amsat/query', json={'params': {}})
    assert amsat.status_code == 200
    assert amsat.json()['memories'][0]['name'] == 'TestSat'
    assert amsat.json()['memories'][0]['freq'] == 145850000

    satnogs = client.post('/api/sources/satnogs/query', json={
        'params': {'modes': ['FM']},
    })
    assert satnogs.status_code == 200
    assert satnogs.json()['memories'][0]['name'] == 'Orbiter VHF'
    assert satnogs.json()['memories'][0]['mode'] == 'NFM'


def test_mapy73_source_parses_mocked_csv_snapshot(client, monkeypatch):
    """Parse mapy73.pl CSV snapshots using an offline response."""
    content = base64.b64decode(csv_image())

    class Response:
        def raise_for_status(self):
            return None

        def iter_lines(self):
            return iter(content.splitlines())

    def get(url, **kwargs):
        assert url == mapy73pl.BASE_URL + 'pl-fmpoland'
        return Response()

    monkeypatch.setattr(mapy73pl.requests, 'get', get)
    response = client.post('/api/sources/mapy73/query', json={
        'params': {'api_option': 'pl-fmpoland'},
    })
    assert response.status_code == 200
    assert response.json()['memories'][0]['name'] == 'TEST'


def test_search_delete_and_export_csv(client):
    """Search the open image, delete a selected channel, and export CSV."""
    assert client.post('/api/session/open', json={
        'filename': 'channels.csv',
        'data_base64': csv_image(),
    }).status_code == 200

    searched = client.get('/api/memories?search=TEST&sort=name')
    assert searched.status_code == 200
    assert searched.json()['total'] == 1
    assert searched.json()['memories'][0]['name'] == 'TEST'

    deleted = client.post('/api/memories/delete', json={'numbers': [0]})
    assert deleted.status_code == 200
    assert deleted.json()['deleted'] == 1
    assert client.get('/api/session').json()['dirty'] is True

    exported = client.get('/api/session/export.csv')
    assert exported.status_code == 200
    rows = list(csv.reader(io.StringIO(exported.text)))
    assert rows[0][:3] == ['Location', 'Name', 'Frequency']
    assert len(rows) == 1


def test_memory_search_uses_display_frequency_and_sorts(client):
    """Search frequencies as displayed and sort both directions."""
    first = chirp_common.Memory(0)
    first.name = 'Alpha'
    first.freq = 146520000
    second = chirp_common.Memory(1)
    second.name = 'Bravo'
    second.freq = 145500000
    assert client.post('/api/session/open', json={
        'filename': 'channels.csv',
        'data_base64': csv_image_with_memories([first, second]),
    }).status_code == 200

    searched = client.get('/api/memories?search=146.520')
    assert searched.status_code == 200
    assert [row['number'] for row in searched.json()['memories']] == [0]

    ascending = client.get('/api/memories?sort=freq')
    descending = client.get('/api/memories?sort=freq&direction=desc')
    assert [row['number'] for row in
            ascending.json()['memories'][:2]] == [1, 0]
    assert [row['number'] for row in
            descending.json()['memories'][:2]] == [0, 1]


def test_import_file_merges_into_empty_memory_slots(client):
    """Merge an uploaded channel list without replacing existing memories."""
    assert client.post('/api/session/open', json={
        'filename': 'channels.csv',
        'data_base64': csv_image(),
    }).status_code == 200

    imported = client.post('/api/session/import', json={
        'filename': 'extra.csv',
        'data_base64': csv_image(),
    })
    assert imported.status_code == 200
    assert imported.json()['imported'] == 1
    assert imported.json()['source_count'] == 1
    assert client.get('/api/memories?start=0&limit=2').json()[
            'memories'][0]['name'] == 'TEST'
    assert client.get('/api/memories?start=1&limit=1').json()[
            'memories'][0]['name'] == 'TEST'


def test_import_file_extends_unbounded_csv_image(client):
    """Append imported memories when an unbounded CSV image has no gaps."""
    memories = []
    for number in range(50):
        memory = chirp_common.Memory(number)
        memory.name = f'CH{number}'
        memory.freq = 146520000
        memories.append(memory)
    assert client.post('/api/session/open', json={
        'filename': 'full.csv',
        'data_base64': csv_image_with_memories(memories),
    }).status_code == 200

    imported = client.post('/api/session/import', json={
        'filename': 'extra.csv',
        'data_base64': csv_image(),
    })
    assert imported.status_code == 200
    assert client.get('/api/memories?start=50&limit=1').json()[
            'memories'][0]['name'] == 'TEST'
    assert client.get('/api/session/history').json()['can_undo'] is True
    assert client.post('/api/session/undo').status_code == 200
    assert client.get('/api/memories?start=50&limit=1').json()[
            'memories'][0]['empty'] is True
    assert client.post('/api/session/redo').status_code == 200
    assert client.get('/api/memories?start=50&limit=1').json()[
            'memories'][0]['name'] == 'TEST'


def test_network_source_query_and_import(client, monkeypatch):
    """Search a network source and import selected results into empty slots."""
    class FakeSource:
        def do_fetch(self, status, params):
            assert params == {'city': 'Town'}
            self.memories = [chirp_common.Memory(0)]
            self.memories[0].name = 'Repeater'
            self.memories[0].freq = 146520000
            status.send_end()

        def get_features(self):
            features = chirp_common.RadioFeatures()
            features.memory_bounds = (0, len(self.memories) - 1)
            return features

        def get_memory(self, number):
            return self.memories[number]

    monkeypatch.setitem(
            web_api.SOURCE_CATALOG, 'test-source', {
                'name': 'Test source',
                'radio': FakeSource,
                'example': {},
                'help': '',
            })
    opened = client.post('/api/session/open', json={
        'filename': 'channels.csv',
        'data_base64': csv_image(),
    })
    assert opened.status_code == 200

    queried = client.post('/api/sources/test-source/query', json={
        'params': {'city': 'Town'},
    })
    assert queried.status_code == 200
    assert queried.json()['memories'][0]['name'] == 'Repeater'

    imported = client.post('/api/sources/import', json={
        'query_id': queried.json()['query_id'],
        'selected': [0],
    })
    assert imported.status_code == 200
    assert imported.json()['imported'] == 1
    assert client.get('/api/memories?start=1&limit=1').json()[
            'memories'][0]['name'] == 'Repeater'
    assert client.get('/api/session').json()['dirty'] is True


def test_radioreference_query_uses_submitted_credentials(client, monkeypatch):
    """Keep RadioReference credentials in the server-side source instance."""
    class FakeRadioReference:
        def __init__(self):
            self.memories = []

        def set_auth(self, username, password):
            self.auth = (username, password)

        def do_fetch(self, status, params):
            assert self.auth == ('operator', 'secret')
            assert params == {'country': 'US', 'zipcounty': '90210'}
            self.memories = [chirp_common.Memory(0)]
            self.memories[0].name = 'Private result'
            status.send_end()

        def get_features(self):
            features = chirp_common.RadioFeatures()
            features.memory_bounds = (0, 0)
            return features

        def get_memory(self, number):
            return self.memories[number]

    monkeypatch.setitem(
            web_api.SOURCE_CATALOG, 'radioreference', {
                'name': 'RadioReference',
                'radio': FakeRadioReference,
                'example': {},
                'help': '',
            })

    response = client.post('/api/sources/radioreference/query', json={
        'params': {
            'username': 'operator',
            'password': 'secret',
            'country': 'US',
            'zipcounty': '90210',
        },
    })

    assert response.status_code == 200
    assert response.json()['memories'][0]['name'] == 'Private result'
    assert 'secret' not in response.text


def test_replacing_unsaved_image_requires_confirmation(client):
    """Protect unsaved channel edits when opening another image."""
    opened = client.post('/api/session/open', json={
        'filename': 'channels.csv',
        'data_base64': csv_image(),
    })
    assert opened.status_code == 200
    changed = client.patch('/api/memories/0', json={'name': 'CHANGED'})
    assert changed.status_code == 200

    unconfirmed = client.post('/api/session/open', json={
        'filename': 'replacement.csv',
        'data_base64': csv_image(),
    })
    assert unconfirmed.status_code == 409
    assert client.get('/api/memories?start=0&limit=1').json()[
            'memories'][0]['name'] == 'CHANGED'

    confirmed = client.post('/api/session/open', json={
        'filename': 'replacement.csv',
        'data_base64': csv_image(),
        'confirm_replace': True,
    })
    assert confirmed.status_code == 200
    assert client.get('/api/memories?start=0&limit=1').json()[
            'memories'][0]['name'] == 'TEST'


@pytest.mark.parametrize('payload', [
    {'freq': -1},
    {'name': None},
    {'unknown_radio_field': 1},
])
def test_memory_updates_reject_invalid_fields(client, payload):
    """Reject invalid edits without marking the image dirty."""
    response = client.post('/api/session/open', json={
        'filename': 'channels.csv',
        'data_base64': csv_image(),
    })
    assert response.status_code == 200

    changed = client.patch('/api/memories/0', json=payload)
    assert changed.status_code == 422
    assert client.get('/api/session').json()['dirty'] is False


def test_bank_models_are_exposed_and_toggled(client):
    """Expose bank layouts from the radio model and allow membership edits."""
    radio = BankedRadio(None)
    client.app.state.session._replace_radio(radio, 'banks.img', None)

    listing = client.get('/api/banks')
    assert listing.status_code == 200
    payload = listing.json()
    assert payload['supported'] is True
    assert payload['models'][0]['name'] == 'Test banks'
    assert payload['models'][0]['mappings'][0]['members'] == [1, 3, 5]

    toggled = client.patch('/api/memories/2/banks', json={
        'model': 'Test banks',
        'bank_index': 0,
        'enabled': True,
    })
    assert toggled.status_code == 200
    assert toggled.json()['enabled'] is True
    assert client.get('/api/banks').json()['models'][0]['mappings'][0]['members'] == [1, 2, 3, 5]

    removed = client.patch('/api/memories/3/banks', json={
        'model': 'Test banks',
        'bank_index': 0,
        'enabled': False,
    })
    assert removed.status_code == 200
    assert client.get('/api/banks').json()['models'][0]['mappings'][0]['members'] == [1, 2, 5]


def test_radio_settings_can_be_loaded_and_updated(client):
    """Expose driver settings and apply validated changes to the image."""
    class SettingsRadio(FakeLiveRadio):
        def set_settings(self, updated):
            self.settings['knob'] = updated[0]['knob'].value.get_value()

    radio = SettingsRadio(None)
    client.app.state.session._replace_radio(radio, 'settings.img', None)

    response = client.get('/api/settings')
    assert response.status_code == 200
    setting = response.json()['groups'][0]['children'][0]
    assert setting['label'] == 'A knob'
    assert setting['type'] == 'integer'
    assert setting['value'] == 5
    assert setting['path'] == ['top', 'knob']

    changed = client.patch('/api/settings', json={
        'changes': [{'path': ['top', 'knob'], 'value': 8}],
    })
    assert changed.status_code == 200
    assert client.get('/api/session').json()['dirty'] is True
    assert client.get('/api/settings').json()[
            'groups'][0]['children'][0]['value'] == 8

    invalid = client.patch('/api/settings', json={
        'changes': [{'path': ['top', 'knob'], 'value': 11}],
    })
    assert invalid.status_code == 422


def test_radio_setting_warnings_require_confirmation(client):
    """Honor driver-provided warnings before applying radio settings."""
    class WarnRadio(FakeLiveRadio):
        def get_settings(self):
            setting = settings.RadioSetting(
                    'enabled', 'Enabled',
                    settings.RadioSettingValueBoolean(False))
            setting.set_warning(
                    'This changes a radio-wide feature.',
                    safe_value=False)
            return settings.RadioSettings(
                    settings.RadioSettingGroup('top', 'Top', setting))

        def set_settings(self, updated):
            self.enabled = updated[0]['enabled'].value.get_value()

    client.app.state.session._replace_radio(
            WarnRadio(None), 'settings.img', None)
    payload = {'changes': [{'path': ['top', 'enabled'], 'value': True}]}

    unconfirmed = client.patch('/api/settings', json=payload)
    assert unconfirmed.status_code == 409
    assert 'This changes a radio-wide feature.' in unconfirmed.json()['detail']

    confirmed = client.patch('/api/settings', json={
        **payload, 'confirm_warnings': True,
    })
    assert confirmed.status_code == 200
    assert confirmed.json()['warnings'] == [
        'This changes a radio-wide feature.']


def test_unknown_image_is_a_client_error(client):
    """Report unsupported images as a client error, not a server crash."""
    response = client.post('/api/session/open', json={
        'filename': 'not-a-radio.img',
        'data_base64': base64.b64encode(b'not a radio image').decode('ascii'),
    })
    assert response.status_code == 422
    assert 'supported radio driver' in response.json()['detail']


def test_radio_transfer_requires_local_port_and_confirmation(client):
    """Require an open clone image before accepting an upload operation."""
    response = client.post(
            '/api/transfers/upload', json={
                'port': '/dev/not-detected',
                'confirm': True,
            })
    assert response.status_code == 409


def test_special_channels_and_hide_empty_are_listed(client):
    """Expose named special channels and allow a filtered empty view."""
    radio = FakeLiveRadio(None)
    radio.memories[-1].empty = False
    radio.memories[-1].freq = 146520000
    client.app.state.session._replace_radio(radio, 'special.img', None)

    visible = client.get('/api/memories?start=11&limit=10')
    assert visible.status_code == 200
    assert visible.json()['memories'][0]['number'] == 'Special'
    filtered = client.get('/api/memories?hide_empty=true')
    assert filtered.status_code == 200
    assert all(not memory['empty'] for memory in filtered.json()['memories'])
    assert filtered.json()['total'] == 6
    changed = client.patch('/api/memories/Special', json={'name': 'CALL'})
    assert changed.status_code == 200
    assert changed.json()['memory']['number'] == 'Special'


def test_memory_move_insert_clipboard_and_shift_delete(client):
    """Support reversible channel arrangement and explicit clipboard paste."""
    first = chirp_common.Memory(0)
    first.name, first.freq = 'FIRST', 146520000
    second = chirp_common.Memory(1)
    second.name, second.freq = 'SECOND', 147000000
    assert client.post('/api/session/open', json={
        'filename': 'channels.csv',
        'data_base64': csv_image_with_memories([first, second]),
    }).status_code == 200

    copied = client.post('/api/memories/copy', json={'numbers': [0]})
    assert copied.status_code == 200
    pasted = client.post('/api/memories/paste', json={
        'clipboard_id': copied.json()['clipboard_id'],
        'start': 2,
    })
    assert pasted.status_code == 200
    assert client.get('/api/memories?start=2&limit=1').json()[
        'memories'][0]['name'] == 'FIRST'

    moved = client.post('/api/memories/move', json={
        'numbers': [1], 'direction': 'up',
    })
    assert moved.status_code == 200
    assert client.get('/api/memories?start=0&limit=2').json()[
        'memories'][0]['name'] == 'SECOND'
    inserted = client.post('/api/memories/insert', json={'number': 0})
    assert inserted.status_code == 200
    assert client.get('/api/memories?start=0&limit=1').json()[
        'memories'][0]['empty'] is True

    deleted = client.post('/api/memories/delete', json={
        'numbers': [1], 'shift': 'all',
    })
    assert deleted.status_code == 200
    assert client.get('/api/session/history').json()['can_undo'] is True


def test_create_blank_and_stock_configurations(client):
    """Open a blank image or one of the built-in starter layouts."""
    templates = client.get('/api/configurations')
    assert templates.status_code == 200
    assert {'id': 'blank', 'name': 'Blank CSV image'} in templates.json()
    created = client.post('/api/session/new', json={
        'template_id': '2m-simplex',
    })
    assert created.status_code == 200
    assert created.json()['filename'] == '2m-simplex.csv'
    rows = client.get('/api/memories?start=1&limit=2').json()['memories']
    assert [row['name'] for row in rows] == ['2M CALL', '2M SIMPLEX']

    stock = client.post('/api/session/new', json={
        'template_id': 'US FRS and GMRS Channels.csv',
    })
    assert stock.status_code == 200
    assert stock.json()['filename'] == 'US FRS and GMRS Channels.csv'
    frs = client.get('/api/memories?start=1&limit=1').json()['memories'][0]
    assert frs['name'] == 'FRS 1'
    assert frs['freq'] == 462562500
    stock_templates = [
        item for item in templates.json()
        if item['id'].endswith('.csv')
    ]
    assert len(stock_templates) == 20


def test_bulk_memory_edit_is_atomic_and_undoable(client):
    """Apply shared edits to selected channels as one history operation."""
    first = chirp_common.Memory(0)
    first.name, first.freq = 'FIRST', 146520000
    second = chirp_common.Memory(1)
    second.name, second.freq = 'SECOND', 147000000
    assert client.post('/api/session/open', json={
        'filename': 'channels.csv',
        'data_base64': csv_image_with_memories([first, second]),
    }).status_code == 200

    updated = client.patch('/api/memories/bulk', json={
        'numbers': [0, 1],
        'changes': {'mode': 'NFM'},
    })
    assert updated.status_code == 200
    assert updated.json()['updated'] == 2
    rows = client.get('/api/memories?start=0&limit=2').json()['memories']
    assert [row['mode'] for row in rows] == ['NFM', 'NFM']
    assert client.post('/api/session/undo').status_code == 200
    rows = client.get('/api/memories?start=0&limit=2').json()['memories']
    assert [row['mode'] for row in rows] == ['FM', 'FM']


def test_selected_channels_can_be_sorted_and_clustered(client):
    """Sort a contiguous selection and group used memories into its gaps."""
    memories = []
    for number, name in enumerate(('ZULU', 'ALPHA', 'BRAVO')):
        memory = chirp_common.Memory(number)
        memory.name = name
        memory.freq = 146520000 + number * 25000
        memories.append(memory)
    assert client.post('/api/session/open', json={
        'filename': 'channels.csv',
        'data_base64': csv_image_with_memories(memories),
    }).status_code == 200

    sorted_result = client.post('/api/memories/arrange', json={
        'numbers': [0, 1, 2], 'operation': 'sort', 'field': 'name',
    })
    assert sorted_result.status_code == 200
    rows = client.get('/api/memories?start=0&limit=3').json()['memories']
    assert [row['name'] for row in rows] == ['ALPHA', 'BRAVO', 'ZULU']

    erased = client.post('/api/memories/delete', json={'numbers': [1]})
    assert erased.status_code == 200
    clustered = client.post('/api/memories/arrange', json={
        'numbers': [0, 1, 2], 'operation': 'cluster',
    })
    assert clustered.status_code == 200
    rows = client.get('/api/memories?start=0&limit=3').json()['memories']
    assert [row['empty'] for row in rows] == [False, False, True]


def test_tx_frequency_workflow_and_tab_snapshot_preserve_edits(client):
    """Edit TX frequency and snapshot without saving the image."""
    assert client.post('/api/session/open', json={
        'filename': 'channels.csv', 'data_base64': csv_image(),
    }).status_code == 200
    changed = client.patch('/api/memories/0', json={
        'txfreq': 145000000,
    })
    assert changed.status_code == 200
    assert changed.json()['memory']['duplex'] == 'split'
    assert changed.json()['memory']['offset'] == 145000000
    snapshot = client.post('/api/session/save?preserve_dirty=true')
    assert snapshot.status_code == 200
    assert snapshot.json()['data_base64']
    assert client.get('/api/session').json()['dirty'] is True


def test_download_runs_as_job_and_opens_image(client, monkeypatch):
    """Run a simulated clone download without attached radio hardware."""

    class FakeSerial:
        is_open = True

        def __init__(self, **kwargs):
            self.port = kwargs['port']

        def close(self):
            self.is_open = False

    class FakeRadio(chirp_common.CloneModeRadio):
        VENDOR = 'Test'
        MODEL = 'WebRadio'

        def sync_in(self):
            self.status_fn(SimpleNamespace(cur=1, max=2, msg='Reading'))

        def save_mmap(self, filename):
            Path(filename).write_bytes(b'fake radio image')

        def get_features(self):
            features = chirp_common.RadioFeatures()
            features.memory_bounds = (0, 0)
            return features

    radio_id = 'Test_WebRadio'
    monkeypatch.setitem(
            service.directory.DRV_TO_RADIO, radio_id, FakeRadio)
    monkeypatch.setattr(
            service.TransferManager, 'ports',
            staticmethod(lambda: [{'port': '/dev/fake-radio'}]))
    monkeypatch.setattr(service.serial, 'Serial', FakeSerial)

    response = client.post('/api/transfers/download', json={
        'radio_id': radio_id,
        'port': '/dev/fake-radio',
    })
    assert response.status_code == 200
    job_id = response.json()['id']
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        status = client.get(f'/api/transfers/{job_id}').json()
        if status['state'] != 'running':
            break
        time.sleep(0.01)

    assert status['state'] == 'complete'
    session = client.get('/api/session').json()
    assert session['name'] == 'Test WebRadio'
    assert session['filename'] == 'Test WebRadio.img'
    assert session['supports_upload'] is True


def test_upload_requires_confirmation_and_runs_job(client, monkeypatch):
    """Require explicit consent before a simulated radio write."""
    calls = []

    class FakeSerial:
        is_open = True

        def __init__(self, **kwargs):
            self.port = kwargs['port']

        def close(self):
            self.is_open = False

    class FakeRadio(chirp_common.CloneModeRadio):
        VENDOR = 'Test'
        MODEL = 'WebRadio'

        def sync_out(self):
            calls.append(self.pipe.port)

        def get_features(self):
            features = chirp_common.RadioFeatures()
            features.memory_bounds = (0, 0)
            return features

    monkeypatch.setattr(
            service.TransferManager, 'ports',
            staticmethod(lambda: [{'port': '/dev/fake-radio'}]))
    monkeypatch.setattr(service.serial, 'Serial', FakeSerial)
    radio = FakeRadio(None)
    client.app.state.session._replace_radio(radio, 'program.img', None)

    unconfirmed = client.post('/api/transfers/upload', json={
        'port': '/dev/fake-radio',
        'confirm': False,
    })
    assert unconfirmed.status_code == 400
    assert calls == []

    response = client.post('/api/transfers/upload', json={
        'port': '/dev/fake-radio',
        'confirm': True,
    })
    assert response.status_code == 200
    job_id = response.json()['id']
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        status = client.get(f'/api/transfers/{job_id}').json()
        if status['state'] != 'running':
            break
        time.sleep(0.01)

    assert status['state'] == 'complete'
    assert calls == ['/dev/fake-radio']
