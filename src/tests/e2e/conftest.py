"""Fixtures for installed-package browser and HTTP end-to-end tests."""


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


import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
import requests


ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def running_web_app(tmp_path):
    """Run the actual package entry module on an unused loopback port."""
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    base_url = f'http://127.0.0.1:{port}'
    log_path = tmp_path / 'web-app.log'
    env = os.environ.copy()
    env['PYTHONPATH'] = os.pathsep.join(filter(None, [
        str(ROOT / 'src'), env.get('PYTHONPATH', ''),
    ]))

    with log_path.open('w+b') as log_file:
        process = subprocess.Popen(
            [sys.executable, '-m', 'chirp_web.webui.main',
             '--no-browser', '--port', str(port)],
            cwd=ROOT,
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
        )
        try:
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    log_file.flush()
                    raise RuntimeError(
                        'Web application exited during startup:\n' +
                        log_path.read_text())
                try:
                    response = requests.get(base_url, timeout=0.25)
                    if response.status_code == 200:
                        break
                except requests.ConnectionError:
                    time.sleep(0.05)
            else:
                raise RuntimeError(
                    'Web application did not start:\n' +
                    log_path.read_text())
            yield base_url
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
