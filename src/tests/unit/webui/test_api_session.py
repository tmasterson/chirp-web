"""Session, diagnostics, and local-interface API tests."""


# Copyright 2026 Tom Masterson <kd7cyu@gmail.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.


import base64
import csv
import io
import zipfile
from types import SimpleNamespace

from chirp_web import chirp_common, settings
from chirp_web.drivers.fake import FakeLiveRadio
from chirp_web.webui import service

from tests.unit.webui.api_test_support import (
        NamedIndexedBankRadio, csv_image, csv_image_with_memories)


def test_home_and_loopback_request_guard(client):
    """Serve the home page but reject remote hosts and cross-origin callers."""
    home = client.get('/')
    assert home.status_code == 200
    assert '<title data-i18n="pageTitle">CHIRP Web</title>' in home.text
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
    about = client.get('/api/about')
    assert about.status_code == 200
    assert about.json()['release_url'].startswith('https://')


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


def test_image_tabs_keep_independent_images_and_histories(client):
    """Keep server-owned images and undo state independent per tab."""
    first = client.post('/api/session/open', json={
        'filename': 'first.csv', 'data_base64': csv_image(),
    }).json()
    assert client.patch(
            '/api/memories/0', json={'name': 'FIRST'}).status_code == 200
    second = client.post('/api/session/open', json={
        'filename': 'second.csv', 'data_base64': csv_image(),
        'confirm_replace': True,
    }).json()
    assert second['tab_id'] != first['tab_id']
    tabs = client.get('/api/session/tabs').json()
    assert {tab['filename'] for tab in tabs['tabs']} == {
        'first.csv', 'second.csv',
    }
    restored = client.post(
        f"/api/session/tabs/{first['tab_id']}/activate").json()
    assert restored['tab_id'] == first['tab_id']
    assert client.get('/api/memories?start=0&limit=1').json()[
        'memories'][0]['name'] == 'FIRST'
    assert client.post('/api/session/undo').status_code == 200


def test_tabs_can_be_reordered_and_request_scoped(client):
    """Keep the request's image tab selected while preserving its order."""
    first = client.post('/api/session/open', json={
        'filename': 'first.csv', 'data_base64': csv_image(),
    }).json()
    second = client.post('/api/session/open', json={
        'filename': 'second.csv', 'data_base64': csv_image(),
        'confirm_replace': True,
    }).json()
    ordered = client.put('/api/session/tabs', json={
        'tab_ids': [second['tab_id'], first['tab_id']],
    })
    assert ordered.status_code == 200
    assert [tab['id'] for tab in ordered.json()['tabs']] == [
        second['tab_id'], first['tab_id']]
    scoped = client.get('/api/session', headers={
        'X-Chirp-Tab': first['tab_id'],
    })
    assert scoped.status_code == 200
    assert scoped.json()['tab_id'] == first['tab_id']


def test_subdevice_selection_changes_the_editing_context(client):
    """Select each sub-device without discarding the parent image tab."""
    class ModuleA(FakeLiveRadio):
        MODEL = 'Module A'

    class ModuleB(FakeLiveRadio):
        MODEL = 'Module B'

    class ParentRadio(FakeLiveRadio):
        def __init__(self):
            super().__init__(None)
            self.children = [ModuleA(None), ModuleB(None)]

        def get_features(self):
            features = super().get_features()
            features.has_sub_devices = True
            return features

        def get_sub_devices(self):
            return self.children

    client.app.state.session._replace_radio(ParentRadio(), 'parent.img', None)
    session = client.get('/api/session')
    assert [item['name'] for item in session.json()['subdevices']] == [
        'CHIRP Module A', 'CHIRP Module B']
    switched = client.post('/api/session/subdevices/1')
    assert switched.status_code == 200
    assert switched.json()['selected_subdevice'] == 1
    assert switched.json()['name'] == 'CHIRP Module B'


def test_selected_memories_can_be_compared_between_open_tabs(client):
    """Expose field-level differences for a channel in another image tab."""
    first = chirp_common.Memory(0)
    first.name, first.freq = 'FIRST', 146520000
    second = chirp_common.Memory(0)
    second.name, second.freq = 'SECOND', 147000000
    left = client.post('/api/session/open', json={
        'filename': 'left.csv',
        'data_base64': csv_image_with_memories([first]),
    }).json()
    client.post('/api/session/open', json={
        'filename': 'right.csv',
        'data_base64': csv_image_with_memories([second]),
        'confirm_replace': True,
    })
    compared = client.post('/api/session/compare-tab', json={
        'tab_id': left['tab_id'], 'numbers': [0],
    })
    assert compared.status_code == 200
    assert compared.json()['comparisons'][0]['changes']['name'] == {
        'current': 'SECOND', 'other': 'FIRST'}


def test_radio_info_diagnostics_and_structured_filters(client):
    """Expose safe support information and validated advanced filters."""
    assert client.post('/api/session/open', json={
        'filename': 'channels.csv', 'data_base64': csv_image(),
    }).status_code == 200
    info = client.get('/api/session/info')
    assert info.status_code == 200
    assert info.json()['driver']['class'] == 'CSVRadio'
    bundle = client.get('/api/session/diagnostics')
    assert bundle.status_code == 200
    with zipfile.ZipFile(io.BytesIO(bundle.content)) as archive:
        assert 'radio-info.json' in archive.namelist()
        assert 'serial-trace.txt' in archive.namelist()
        assert 'mem_extra' not in archive.read('radio-info.json').decode()
    filtered = client.post('/api/memories/query', json={
        'filters': [{
            'field': 'name', 'operator': 'contains', 'value': 'TES',
        }],
    })
    assert filtered.status_code == 200
    assert filtered.json()['total'] == 1


def test_advanced_diagnostics_require_opt_in_and_redact_transfer_trace(client):
    """Keep raw inspection explicit while exposing safe trace entries."""
    first = chirp_common.Memory(0)
    first.name = 'FIRST'
    first.freq = 146520000
    second = chirp_common.Memory(1)
    second.name = 'SECOND'
    second.freq = 446000000
    assert client.post('/api/session/open', json={
        'filename': 'channels.csv',
        'data_base64': csv_image_with_memories([first, second]),
    }).status_code == 200
    assert client.get('/api/session/transfer-trace').json() == {
        'entries': [],
    }
    raw = client.post('/api/memories/raw', json={'numbers': [0]})
    assert raw.status_code == 409
    enabled = client.patch('/api/session/advanced-diagnostics', json={
        'enabled': True,
    })
    assert enabled.status_code == 200
    assert enabled.json() == {'enabled': True}
    raw = client.post('/api/memories/raw', json={'numbers': [0]})
    assert raw.status_code == 200
    assert raw.json()['memories'][0]['number'] == 0
    assert raw.json()['memories'][0]['raw']
    compared = client.post('/api/memories/raw-diff', json={
        'numbers': [0, 1],
    })
    assert compared.status_code == 200
    assert 'channel-0' in compared.json()['diff']
    assert 'channel-1' in compared.json()['diff']


def test_support_report_and_recovery_are_explicit_and_local(client):
    """Let users review support files and restore downloaded image drafts."""
    opened = client.post('/api/session/open', json={
        'filename': 'channels.csv', 'data_base64': csv_image(),
    })
    assert opened.status_code == 200
    manifest = client.get('/api/session/report-manifest')
    assert manifest.status_code == 200
    assert {item['id'] for item in manifest.json()['files']} == {
        'radio-info', 'serial-trace', 'backups',
    }
    report = client.post('/api/session/report', json={
        'include': ['radio-info', 'serial-trace'],
    })
    assert report.status_code == 200
    with zipfile.ZipFile(io.BytesIO(report.content)) as archive:
        assert set(archive.namelist()) == {
            'radio-info.json', 'serial-trace.txt',
        }
    recovery = client.post('/api/session/recovery/export')
    assert recovery.status_code == 200
    assert recovery.json()['tabs'][0]['filename'] == 'channels.csv'
    assert client.post('/api/session/close').status_code == 200
    restored = client.post('/api/session/recovery/import', json={
        'tabs': recovery.json()['tabs'],
    })
    assert restored.status_code == 200
    assert client.get('/api/memories?start=0&limit=1').json()[
        'memories'][0]['name'] == 'TEST'


def test_port_detection_and_explicit_local_ports(client, monkeypatch):
    """Expose plug-in detection and permit explicit local serial paths."""
    monkeypatch.setattr(
            service.TransferManager, 'ports',
            staticmethod(lambda: [{
                'port': '/dev/ttyUSB0', 'description': 'First port',
            }, {
                'port': '/dev/ttyUSB1', 'description': 'New port',
            }]))
    detected = client.get('/api/ports/detect', params={
        'baseline': '["/dev/ttyUSB0"]',
    })
    assert detected.status_code == 200
    assert detected.json()['detected'] == [{
        'port': '/dev/ttyUSB1', 'description': 'New port',
    }]
    assert service.TransferManager.valid_port('/dev/custom-radio')
    assert service.TransferManager.valid_port('COM42')
    assert not service.TransferManager.valid_port('not-a-port')


def test_connected_live_radio_requires_explicit_edit_confirmation(client):
    """Reject live changes until the browser confirms their immediate write."""
    radio = FakeLiveRadio(None)
    client.app.state.session._replace_radio(radio, 'live.radio', None)
    client.app.state.session._tab.live_port = SimpleNamespace(is_open=True)
    rejected = client.patch('/api/memories/1', json={'name': 'LIVE'})
    assert rejected.status_code == 409
    accepted = client.patch(
        '/api/memories/1', json={'name': 'LIVE'},
        headers={'X-Chirp-Confirm-Live': 'true'})
    assert accepted.status_code == 200
    assert radio.get_memory(1).name == 'LIVE'


def test_memory_change_can_be_undone_and_redone(client):
    """Keep one-step undo and redo history for memory edits."""
    assert client.post('/api/session/open', json={
        'filename': 'channels.csv', 'data_base64': csv_image(),
    }).status_code == 200
    assert client.patch(
            '/api/memories/0', json={'name': 'UPDATED'}).status_code == 200
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
    """Preview and copy selected memories without replacing the open image."""
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
