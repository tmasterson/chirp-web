"""Serial transfer API tests."""


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


import threading
import time
from pathlib import Path
from types import SimpleNamespace

from chirp_web import chirp_common
from chirp_web.webui import service



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


def test_transfer_prompts_require_confirmation_and_jobs_can_cancel(
        client, monkeypatch):
    """Require driver instructions and cancel a blocked serial operation."""
    started = threading.Event()
    stopped = threading.Event()

    class FakeSerial:
        is_open = True

        def __init__(self, **kwargs):
            self.port = kwargs['port']

        def close(self):
            self.is_open = False
            stopped.set()

    class PromptRadio(chirp_common.CloneModeRadio):
        VENDOR = 'Test'
        MODEL = 'PromptRadio'

        @classmethod
        def get_prompts(cls):
            prompts = chirp_common.RadioPrompts()
            prompts.pre_download = 'Put the radio in clone mode.'
            return prompts

        def sync_in(self):
            started.set()
            assert stopped.wait(3)
            raise RuntimeError('serial port closed')

        def get_features(self):
            features = chirp_common.RadioFeatures()
            features.memory_bounds = (0, 0)
            return features

    radio_id = 'Test_PromptRadio'
    monkeypatch.setitem(service.directory.DRV_TO_RADIO, radio_id, PromptRadio)
    monkeypatch.setattr(
            service.TransferManager, 'ports',
            staticmethod(lambda: [{'port': '/dev/fake-radio'}]))
    monkeypatch.setattr(service.serial, 'Serial', FakeSerial)

    prompts = client.get(f'/api/radios/{radio_id}/prompts')
    assert prompts.status_code == 200
    assert prompts.json()['download']['pre_download']
    rejected = client.post('/api/transfers/download', json={
        'radio_id': radio_id, 'port': '/dev/fake-radio',
    })
    assert rejected.status_code == 409
    started_job = client.post('/api/transfers/download', json={
        'radio_id': radio_id, 'port': '/dev/fake-radio',
        'confirm_prompts': True,
    })
    assert started_job.status_code == 200
    assert started.wait(3)
    cancelled = client.delete(f"/api/transfers/{started_job.json()['id']}")
    assert cancelled.status_code == 200
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        status = client.get(
            f"/api/transfers/{started_job.json()['id']}").json()
        if status['state'] != 'running':
            break
        time.sleep(0.01)
    assert status['state'] == 'cancelled'


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
