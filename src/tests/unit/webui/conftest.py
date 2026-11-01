"""Pytest fixtures for web UI unit tests."""


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


from chirp_web.webui.api import create_app

from fastapi.testclient import TestClient

import pytest


@pytest.fixture
def client():
    """Provide an isolated local API app for each test."""
    with TestClient(
            create_app(), base_url='http://127.0.0.1:8765') as test_client:
        yield test_client
