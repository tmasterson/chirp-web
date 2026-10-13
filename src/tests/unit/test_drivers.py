"""Tests for shared file-format and radio-transfer driver helpers."""

from io import StringIO
from types import SimpleNamespace

from chirp_web import chirp_common, errors, memmap
from chirp_web.drivers import clone_common, generic_csv, wouxun_common

import pytest


def _csv_radio():
    """Return a CSV radio with all slots initialized as empty."""
    radio = generic_csv.CSVRadio(None)
    radio._blank()
    return radio


def test_csv_loads_memories_and_caches_cleaners_by_memory_type():
    """Parse channel fields and cache post-processors between CSV rows."""
    radio = _csv_radio()
    radio._load(StringIO(
        'Location,Name,Frequency,Mode\n'
        '1,Alpha,146.520,FM\n'
        '2,Bravo,147.000,FM\n'))

    first = radio.get_memory(1)
    assert first.name == 'Alpha'
    assert first.freq == 146520000
    assert radio.get_memory(2).name == 'Bravo'
    assert chirp_common.Memory in radio._cleaner_cache


def test_csv_records_bad_rows_and_continues_loading_valid_rows():
    """Skip malformed rows while preserving valid data and errors."""
    radio = _csv_radio()

    radio._load(StringIO(
        'Location,Name,Frequency,Mode\n'
        '1,Alpha,146.520,FM\n'
        '2,Broken,not-a-frequency,FM\n'))

    assert radio.get_memory(1).name == 'Alpha'
    assert len(radio.errors) == 1
    assert 'Line 3' in radio.errors[0]


@pytest.mark.parametrize('contents', ['', '# comment without newline'])
def test_csv_rejects_input_without_channel_rows(contents):
    """Report empty and comment-only files as invalid data."""
    radio = _csv_radio()

    with pytest.raises(errors.InvalidDataError, match='No channels'):
        radio._load(StringIO(contents))


def test_csv_rejects_short_rows_and_keeps_loading():
    """Skip rows missing columns, but accept later well-formed rows."""
    radio = _csv_radio()

    radio._load(StringIO(
        'Location,Name,Frequency,Mode\n'
        '1,Short\n'
        '2,Valid,146.520,FM\n'))

    assert radio.get_memory(2).name == 'Valid'
    assert radio.errors == ['Column number mismatch on line 2']


def test_csv_growth_allocates_only_through_requested_slot():
    """Grow the memory list to the exact requested zero-based index."""
    radio = _csv_radio()
    radio.memories = []

    radio._grow(2)

    assert len(radio.memories) == 3
    assert [memory.number for memory in radio.memories] == [0, 1, 2]
    assert all(memory.empty for memory in radio.memories)


@pytest.mark.parametrize('number', [-1, 1000, None, '1'])
def test_csv_invalid_memory_locations_raise_driver_error(number):
    """Reject invalid indexes instead of leaking indexing exceptions."""
    radio = _csv_radio()

    with pytest.raises(errors.InvalidMemoryLocation):
        radio.get_memory(number)


def test_csv_memory_reads_are_copies_and_writes_grow_the_image():
    """Keep callers from mutating stored channels and grow for writes."""
    radio = _csv_radio()
    memory = chirp_common.Memory(number=1000, name='Channel')
    memory.freq = 146520000

    radio.set_memory(memory)
    fetched = radio.get_memory(1000)
    fetched.name = 'Changed'

    assert radio.get_memory(1000).name == 'Channel'
    assert len(radio.memories) == 1001


@pytest.mark.parametrize(
    ('contents', 'expected'),
    [
        ('Location,Name,Frequency\n', True),
        ('"Location",Name,Frequency\n', True),
        ("'Location',Name,Frequency\n", True),
        ('# comment\nLocation,Name,Frequency\n', True),
        ('# comment without newline', False),
        ('', False),
    ],
)
def test_csv_header_detection_handles_bom_comments_and_empty_data(
        contents, expected):
    """Recognize headers and terminate on unterminated comment lines."""
    assert generic_csv.find_csv_header(contents) is expected


def test_csv_header_detection_skips_bom():
    """Recognize a UTF-8 BOM before the first header."""
    assert generic_csv.find_csv_header('\ufeffLocation,Name\n')


class FakePipe:
    """Provide deterministic serial reads and record writes."""

    def __init__(self, responses):
        """Initialize queued responses and a write log."""
        self.responses = list(responses)
        self.writes = []

    def write(self, data):
        """Record a serial write."""
        self.writes.append(data)

    def read(self, length):
        """Return the next queued response."""
        return self.responses.pop(0)


def test_clone_exit_programming_mode_sends_exit_command():
    """Send the shared exit command to the radio."""
    pipe = FakePipe([])

    clone_common.exit_programming_mode(SimpleNamespace(pipe=pipe))

    assert pipe.writes == [b"E"]


def test_clone_exit_programming_mode_reports_write_errors():
    """Convert serial write failures to a radio error."""
    class BrokenPipe:
        def write(self, data):
            raise OSError("disconnected")

    with pytest.raises(errors.RadioError, match="exit programming mode"):
        clone_common.exit_programming_mode(SimpleNamespace(pipe=BrokenPipe()))


def test_wouxun_download_accumulates_blocks_and_reports_progress():
    """Download multiple blocks into one image and report each block."""
    pipe = FakePipe([
        b'HEADab', b'\x06',
        b'HEADcd', b'\x06',
    ])
    statuses = []
    radio = SimpleNamespace(pipe=pipe, status_fn=statuses.append)

    image = wouxun_common.do_download(radio, 0, 4, 2)

    assert image.get_packed() == b'abcd'
    assert pipe.writes == [b'R\x00\x00\x02', b'\x06',
                           b'R\x00\x02\x02', b'\x06']
    assert [status.cur for status in statuses] == [0, 2]


def test_wouxun_download_rejects_truncated_blocks():
    """Fail immediately if a radio returns less data than the block size."""
    radio = SimpleNamespace(
        pipe=FakePipe([b'short']),
        status_fn=None)

    with pytest.raises(Exception, match='Failed to read full block'):
        wouxun_common.do_download(radio, 0, 2, 2)


def test_wouxun_upload_writes_blocks_and_rejects_bad_acknowledgements():
    """Upload image slices and treat a missing ACK as a transfer failure."""
    pipe = FakePipe([b'\x06', b'\x06'])
    radio = SimpleNamespace(
        pipe=pipe,
        status_fn=None,
        get_mmap=lambda: memmap.MemoryMapBytes(b'abcd'))

    wouxun_common.do_upload(radio, 0, 4, 2)

    assert pipe.writes == [b'W\x00\x00\x02ab', b'W\x00\x02\x02cd']

    radio.pipe = FakePipe([b'\x15'])
    with pytest.raises(Exception, match='did not ack'):
        wouxun_common.do_upload(radio, 0, 2, 2)


def test_wouxun_empty_transfer_does_not_access_the_serial_port():
    """Return an empty image for an empty address range."""
    pipe = FakePipe([])
    radio = SimpleNamespace(pipe=pipe, status_fn=None)

    image = wouxun_common.do_download(radio, 0, 0, 2)

    assert image.get_packed() == b''
    assert pipe.writes == []
