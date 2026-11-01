"""Shared fixtures and radio doubles for web API tests."""


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
import time

from chirp_web import chirp_common
from chirp_web.drivers.fake import FakeLiveRadio


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


def source_result(client, response):
    """Wait for one asynchronous source query to finish."""
    assert response.status_code == 200
    job_id = response.json()['id']
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        job = client.get(f'/api/sources/jobs/{job_id}').json()
        if job['state'] != 'running':
            assert job['state'] == 'complete', job
            return job['result']
        time.sleep(0.01)
    raise AssertionError('Source query did not finish')


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
            mapping = self._bank_model.get_mappings()[0]
            self._bank_model.add_memory_to_mapping(
                    self.get_memory(number), mapping)

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
