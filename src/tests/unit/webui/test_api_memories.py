"""Memory, bank, settings, and image-editing API tests."""


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

from chirp_web import chirp_common, settings
from chirp_web.drivers.fake import FakeLiveRadio

from tests.unit.webui.api_test_support import (
        BankedRadio, csv_image, csv_image_with_memories)

import pytest


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
    assert client.get('/api/banks').json()['models'][0]['mappings'][0][
            'members'] == [1, 2, 3, 5]

    removed = client.patch('/api/memories/3/banks', json={
        'model': 'Test banks',
        'bank_index': 0,
        'enabled': False,
    })
    assert removed.status_code == 200
    assert client.get('/api/banks').json()['models'][0]['mappings'][0][
            'members'] == [1, 2, 5]


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
