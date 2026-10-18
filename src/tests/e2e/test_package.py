"""End-to-end checks for the installed local web application."""

import base64
import csv
import io

import requests


def _channel_csv():
    """Create a valid one-channel file using the public CSV serialization."""
    from chirp_web import chirp_common

    memory = chirp_common.Memory(0)
    memory.name = 'E2E'
    memory.freq = 146520000
    rows = [
        [field for field in chirp_common.Memory.CSV_FORMAT
         if field != 'Power'],
        [value for field, value in zip(
            chirp_common.Memory.CSV_FORMAT, memory.to_csv())
         if field != 'Power'],
    ]
    output = io.StringIO(newline='')
    csv.writer(output).writerows(rows)
    return output.getvalue().encode()


def test_live_package_open_edit_save_and_local_guards(running_web_app):
    """Exercise the CLI, static UI and a complete image edit over HTTP."""
    base_url = running_web_app

    home = requests.get(base_url, timeout=2)
    assert home.status_code == 200
    assert '<title data-i18n="pageTitle">CHIRP Web</title>' in home.text
    assert home.headers['Content-Security-Policy'].startswith(
        "default-src 'self'")
    script = requests.get(f'{base_url}/static/app.js', timeout=2)
    assert script.status_code == 200
    assert 'imageFile' in script.text

    radios = requests.get(f'{base_url}/api/radios', timeout=10)
    assert radios.status_code == 200
    assert radios.json()
    ports = requests.get(f'{base_url}/api/ports', timeout=2)
    assert ports.status_code == 200
    assert isinstance(ports.json(), list)

    image = base64.b64encode(_channel_csv()).decode('ascii')
    opened = requests.post(
        f'{base_url}/api/session/open',
        json={'filename': '../../e2e.csv', 'data_base64': image},
        timeout=10)
    assert opened.status_code == 200
    assert opened.json()['filename'] == 'e2e.csv'
    assert opened.json()['name'] == 'Generic CSV'

    channels = requests.get(
        f'{base_url}/api/memories?start=0&limit=1', timeout=2)
    assert channels.status_code == 200
    assert channels.json()['memories'][0]['name'] == 'E2E'

    changed = requests.patch(
        f'{base_url}/api/memories/0',
        json={'name': 'LIVE', 'freq': 145500000},
        timeout=2)
    assert changed.status_code == 200
    assert changed.json()['memory']['name'] == 'LIVE'
    assert requests.get(f'{base_url}/api/session', timeout=2).json()[
        'dirty'] is True

    saved = requests.post(f'{base_url}/api/session/save', timeout=5)
    assert saved.status_code == 200
    exported = base64.b64decode(saved.json()['data_base64'])
    exported_rows = list(csv.reader(io.StringIO(
        exported.decode('utf-8'))))
    header = exported_rows[0]
    row = exported_rows[1]
    assert row[header.index('Name')] == 'LIVE'
    assert row[header.index('Frequency')] == '145.500000'
    assert requests.get(f'{base_url}/api/session', timeout=2).json()[
        'dirty'] is False

    wrong_host = requests.get(
        base_url, headers={'Host': 'radio.example'}, timeout=2)
    assert wrong_host.status_code == 403
    wrong_origin = requests.get(
        base_url, headers={'Origin': 'https://radio.example'}, timeout=2)
    assert wrong_origin.status_code == 403

    unsupported = requests.post(
        f'{base_url}/api/session/open',
        json={
            'filename': 'bad.img',
            'data_base64': base64.b64encode(b'not a radio image').decode(),
        },
        timeout=5)
    assert unsupported.status_code == 422
