"""External source-query API tests."""


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
from pathlib import Path

from chirp_web import chirp_common
from chirp_web.sources import mapy73pl, satellites
from chirp_web.webui import api as web_api

from tests.unit.webui.api_test_support import (
        csv_image, csv_image_with_memories, source_result)


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
    amsat = source_result(
        client, client.post('/api/sources/amsat/query', json={'params': {}}))
    assert amsat['memories'][0]['name'] == 'TestSat'
    assert amsat['memories'][0]['freq'] == 145850000

    satnogs = source_result(
            client, client.post('/api/sources/satnogs/query', json={
                'params': {'modes': ['FM']},
            }))
    assert satnogs['memories'][0]['name'] == 'Orbiter VHF'
    assert satnogs['memories'][0]['mode'] == 'NFM'


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
    response = source_result(
            client, client.post('/api/sources/mapy73/query', json={
                'params': {'api_option': 'pl-fmpoland'},
            }))
    assert response['memories'][0]['name'] == 'TEST'


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


def test_import_file_supports_matching_append_and_destination_range(client):
    """Place file imports explicitly without changing the safe default."""
    original = chirp_common.Memory(0)
    original.name, original.freq = 'ORIGINAL', 146520000
    occupied = chirp_common.Memory(3)
    occupied.name, occupied.freq = 'OCCUPIED', 146620000
    imported_memory = chirp_common.Memory(0)
    imported_memory.name, imported_memory.freq = 'IMPORTED', 146720000
    assert client.post('/api/session/open', json={
        'filename': 'channels.csv',
        'data_base64': csv_image_with_memories([original, occupied]),
    }).status_code == 200
    payload = {
        'filename': 'source.csv',
        'data_base64': csv_image_with_memories([imported_memory]),
    }

    matching = client.post('/api/session/import', json={
        **payload, 'placement': 'matching',
    })
    assert matching.status_code == 200
    assert client.get('/api/memories?start=0&limit=1').json()[
        'memories'][0]['name'] == 'IMPORTED'

    appended = client.post('/api/session/import', json={
        **payload, 'placement': 'append',
    })
    assert appended.status_code == 200
    assert client.get('/api/memories?start=4&limit=1').json()[
        'memories'][0]['name'] == 'IMPORTED'

    ranged = client.post('/api/session/import', json={
        **payload, 'placement': 'range', 'destination_start': 3,
    })
    assert ranged.status_code == 200
    assert client.get('/api/memories?start=3&limit=1').json()[
        'memories'][0]['name'] == 'IMPORTED'


def test_print_and_csv_export_use_selected_or_filtered_scopes(client):
    """Keep print preview and CSV download aligned with the chosen scope."""
    first = chirp_common.Memory(0)
    first.name, first.freq = 'ALPHA', 146520000
    second = chirp_common.Memory(1)
    second.name, second.freq = 'BRAVO', 147000000
    assert client.post('/api/session/open', json={
        'filename': 'channels.csv',
        'data_base64': csv_image_with_memories([first, second]),
    }).status_code == 200

    printed = client.post('/api/session/print', json={
        'scope': 'selected', 'numbers': [1],
    })
    assert printed.status_code == 200
    assert [memory['name'] for memory in printed.json()['memories']] == [
        'BRAVO']

    exported = client.post('/api/session/export.csv', json={
        'scope': 'filtered',
        'filters': [{
            'field': 'name', 'operator': 'contains', 'value': 'alp',
        }],
    })
    assert exported.status_code == 200
    rows = list(csv.DictReader(io.StringIO(exported.text)))
    assert [row['Name'] for row in rows] == ['ALPHA']


def test_retained_backups_are_opt_in_and_can_be_restored_or_deleted(
        client, tmp_path):
    """Keep configured backups locally until the user restores or deletes."""
    class BackupRadio(chirp_common.CloneModeRadio):
        def get_features(self):
            features = chirp_common.RadioFeatures()
            features.memory_bounds = (0, 0)
            return features

        def save_mmap(self, filename):
            Path(filename).write_bytes(base64.b64decode(csv_image()))

    session = client.app.state.session
    session._replace_radio(BackupRadio(None), 'program.csv', None)
    configured = client.put('/api/session/backups/settings', json={
        'directory': str(tmp_path), 'retention': 2,
    })
    assert configured.status_code == 200
    assert configured.json()['retention'] == 2
    session.create_backup('upload')
    backups = client.get('/api/session/backups').json()['backups']
    retained = next(item for item in backups if item['persistent'])
    assert (tmp_path / retained['id']).is_file()

    restored = client.post(
        f"/api/session/backups/{retained['id']}/restore")
    assert restored.status_code == 200
    assert restored.json()['filename'] == 'program.csv'
    deleted = client.delete(f"/api/session/backups/{retained['id']}")
    assert deleted.status_code == 200
    assert not (tmp_path / retained['id']).exists()


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

    queried = source_result(
            client, client.post('/api/sources/test-source/query', json={
                'params': {'city': 'Town'},
            }))
    assert queried['memories'][0]['name'] == 'Repeater'

    imported = client.post('/api/sources/import', json={
        'query_id': queried['query_id'],
        'selected': [0],
    })
    assert imported.status_code == 200
    assert imported.json()['imported'] == 1
    assert client.get('/api/memories?start=1&limit=1').json()[
            'memories'][0]['name'] == 'Repeater'
    assert client.get('/api/session').json()['dirty'] is True
    history = client.get('/api/sources/history')
    assert history.status_code == 200
    assert history.json()['jobs'][0]['source_id'] == 'test-source'
    retry = client.post(
        f"/api/sources/history/{history.json()['jobs'][0]['id']}/retry")
    assert source_result(client, retry)['count'] == 1


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

    response = source_result(
            client, client.post('/api/sources/radioreference/query', json={
                'params': {
                    'username': 'operator',
                    'password': 'secret',
                    'country': 'US',
                    'zipcounty': '90210',
                },
            }))

    assert response['memories'][0]['name'] == 'Private result'
    assert 'secret' not in str(response)
    history = client.get('/api/sources/history').json()['jobs'][0]
    assert 'password' not in history['params']
    assert 'username' not in history['params']
