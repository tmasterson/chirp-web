"""Hardware-independent tests for the local web interface."""

import base64
import csv
import io
import time
from pathlib import Path
from types import SimpleNamespace

from chirp_web import chirp_common, settings
from chirp_web.drivers.fake import FakeLiveRadio
from chirp_web.webui import service
from chirp_web.webui import api as web_api
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


def test_home_and_loopback_request_guard(client):
    """Serve the home page but reject remote hosts and cross-origin callers."""
    home = client.get('/')
    assert home.status_code == 200
    assert 'CHIRP Web Web' in home.text
    sources = client.get('/api/sources')
    assert sources.status_code == 200
    assert {source['id'] for source in sources.json()} == {
        'dmrmarc', 'przemienniki-eu', 'przemienniki-net',
        'radioreference', 'repeaterbook',
    }

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
