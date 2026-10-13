# Copyright 2017 Dan Smith <dsmith@danplanet.com>
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

"""Rugged RH5R V2 radio management module."""

import logging
import struct

from chirp_web import bitwise, chirp_common, directory, errors, memmap


LOG = logging.getLogger(__name__)

BLOCK_SIZE = 0x40
DOWNLOAD_SIZE = 0x2000
IDENTIFIER = b'PGM2015'
EMPTY_CHANNEL = b'\xFF\xFF\xFF\xFF'


def _update_status(radio, offset, label='Cloning from radio'):
    if not radio.status_fn:
        return

    status = chirp_common.Status()
    status.cur = offset
    status.max = DOWNLOAD_SIZE
    status.msg = label
    radio.status_fn(status)


def _identify(radio):
    try:
        radio.pipe.write(IDENTIFIER)
        ack = radio.pipe.read(2)
        if ack != b'\x06\x30':
            raise errors.RadioError('Radio did not ACK first command: %r' %
                                    ack)
    except Exception:
        LOG.exception('')
        raise errors.RadioError('Unable to communicate with the radio')


def _download(radio):
    _identify(radio)
    data = bytearray()
    for offset in range(0, DOWNLOAD_SIZE, BLOCK_SIZE):
        msg = struct.pack('>cHb', b'R', offset, BLOCK_SIZE)
        radio.pipe.write(msg)
        block = radio.pipe.read(BLOCK_SIZE + 4)
        if len(block) != (BLOCK_SIZE + 4):
            raise errors.RadioError('Radio sent a short block (%02x/%02x)' % (
                len(block), BLOCK_SIZE + 4))
        data.extend(block[4:])
        _update_status(radio, offset)

    data += IDENTIFIER
    return memmap.MemoryMapBytes(bytes(data))


def _upload(radio):
    _identify(radio)
    for offset in range(0, DOWNLOAD_SIZE, BLOCK_SIZE):
        msg = struct.pack('>cHb', b'W', offset, BLOCK_SIZE)
        msg += radio._mmap[offset:(offset + BLOCK_SIZE)]
        radio.pipe.write(msg)
        ack = radio.pipe.read(1)
        if ack != b'\x06':
            raise errors.RadioError('Radio did not ACK block %i (0x%04x)' % (
                offset, offset))

        _update_status(radio, offset)


MEM_FORMAT = """
struct memory {
  bbcd rx_freq[4];
  bbcd tx_freq[4];
  lbcd rx_tone[2];
  lbcd tx_tone[2];

  u8 unknown10:5,
     highpower:1,
     unknown11:2;
  u8 unknown20:4,
     narrow:1,
     unknown21:3;
  u8 unknown31:1,
     scanadd:1,
     unknown32:6;
  u8 unknown4;
};

struct name {
  char name[7];
};

#seekto 0x0010;
struct memory channels[128];

#seekto 0x08C0;
struct name names[128];

#seekto 0x2020;
struct memory vfo1;
struct memory vfo2;
"""


POWER_LEVELS = [chirp_common.PowerLevel('Low', watts=1),
                chirp_common.PowerLevel('High', watts=5)]


class TYTTHUVF8_V2(chirp_common.CloneModeRadio):
    """Base driver for radios using the TYT TH-UVF8F protocol."""

    VENDOR = 'TYT'
    MODEL = 'TH-UVF8F'
    BAUD_RATE = 9600
    _FILEID = b'OEMOEM \\XFF'

    def get_features(self):
        """Return the capabilities of this radio."""
        rf = chirp_common.RadioFeatures()
        rf.memory_bounds = (1, 128)
        rf.has_bank = False
        rf.has_ctone = True
        rf.valid_tuning_steps = [5, 6.25, 10, 12.5]
        rf.has_tuning_step = False
        rf.has_cross = True
        rf.has_rx_dtcs = True
        rf.has_settings = False
        rf.can_odd_split = False
        rf.valid_duplexes = ['', '-', '+']
        rf.valid_tmodes = ['', 'Tone', 'TSQL', 'DTCS', 'Cross']
        rf.valid_characters = chirp_common.CHARSET_UPPER_NUMERIC + '-'
        rf.valid_bands = [(136000000, 174000000),
                          (400000000, 480000000)]
        rf.valid_skips = ['', 'S']
        rf.valid_power_levels = POWER_LEVELS
        rf.valid_modes = ['FM', 'NFM']
        rf.valid_name_length = 7
        rf.valid_cross_modes = ['Tone->Tone', 'Tone->DTCS', 'DTCS->Tone',
                                '->Tone', '->DTCS', 'DTCS->', 'DTCS->DTCS']
        return rf

    def sync_in(self):
        """Download the radio image and parse its memory map."""
        try:
            self._mmap = _download(self)
        finally:
            try:
                self.pipe.write(b'E')
            except Exception:
                pass

        self.process_mmap()

    def sync_out(self):
        """Upload the current memory map to the radio."""
        try:
            _upload(self)
        finally:
            try:
                self.pipe.write(b'E')
            except Exception:
                pass

    @classmethod
    def match_model(cls, filedata, filename):
        """Return whether the file image belongs to this radio model."""
        return (filedata.endswith(IDENTIFIER) and
                filedata[0x840:0x848] == cls._FILEID)

    def process_mmap(self):
        """Parse the radio memory map."""
        self._memobj = bitwise.parse(MEM_FORMAT, self._mmap)

    def get_raw_memory(self, number):
        """Return the raw channel and name data for a memory."""
        return repr(self._memobj.channels[number - 1]) + repr(
            self._memobj.names[number - 1])

    def _get_memobjs(self, number):
        return (self._memobj.channels[number - 1],
                self._memobj.names[number - 1])

    def _decode_tone(self, toneval):
        val0 = toneval[0].get_bits(0xFF)
        val1 = toneval[1].get_bits(0xFF)
        rawval = (val1 << 8) | val0

        if val0 == 0xFF:
            return '', 0, 'N'

        if (val1 & 0xC0) == 0xC0:
            return 'DTCS', rawval & 0x3FFF, 'R'

        if val1 & 0x80:
            return 'DTCS', rawval & 0x3FFF, 'N'

        return 'Tone', int(toneval) / 10.0, 'N'

    def _encode_tone(self, _toneval, mode, val, pol):
        if mode == 'Tone':
            toneval = int(str(int(val * 10)), 16)
        elif mode == 'DTCS':
            toneval = int(str(int(val)), 16)
            toneval |= 0x8000
            if pol == 'R':
                toneval |= 0x4000
        else:
            toneval = 0xFFFF

        _toneval[0].set_raw(toneval & 0xFF)
        _toneval[1].set_raw((toneval >> 8) & 0xFF)

    def get_memory(self, number):
        """Return a memory decoded from the radio image."""
        _mem, _name = self._get_memobjs(number)

        mem = chirp_common.Memory()
        mem.number = number

        if _mem.get_raw().startswith(EMPTY_CHANNEL):
            mem.empty = True
            return mem

        mem.freq = int(_mem.rx_freq) * 10
        offset = (int(_mem.tx_freq) - int(_mem.rx_freq)) * 10
        if offset == 0:
            mem.offset = 0
            mem.duplex = ''
        elif offset < 0:
            mem.offset = abs(offset)
            mem.duplex = '-'
        else:
            mem.offset = offset
            mem.duplex = '+'

        txmode, txval, txpol = self._decode_tone(_mem.tx_tone)
        rxmode, rxval, rxpol = self._decode_tone(_mem.rx_tone)

        chirp_common.split_tone_decode(mem,
                                       (txmode, txval, txpol),
                                       (rxmode, rxval, rxpol))

        mem.mode = 'NFM' if _mem.narrow else 'FM'
        mem.skip = '' if _mem.scanadd else 'S'
        mem.power = POWER_LEVELS[int(_mem.highpower)]
        mem.name = str(_name.name).rstrip('\xFF ')

        return mem

    def set_memory(self, mem):
        """Encode a memory into the radio image."""
        _mem, _name = self._get_memobjs(mem.number)
        if mem.empty:
            _mem.set_raw(b'\xFF' * 16)
            _name.set_raw(b'\xFF' * 7)
            return

        _mem.set_raw(b'\x00' * 16)

        _mem.rx_freq = mem.freq / 10
        if mem.duplex == '-':
            mult = -1
        elif not mem.duplex:
            mult = 0
        else:
            mult = 1
        _mem.tx_freq = (mem.freq + (mem.offset * mult)) / 10

        (txmode, txval, txpol), (rxmode, rxval, rxpol) = \
            chirp_common.split_tone_encode(mem)

        self._encode_tone(_mem.tx_tone, txmode, txval, txpol)
        self._encode_tone(_mem.rx_tone, rxmode, rxval, rxpol)

        _mem.narrow = mem.mode == 'NFM'
        _mem.scanadd = mem.skip != 'S'
        _mem.highpower = POWER_LEVELS.index(mem.power) if mem.power else 1
        _name.name = mem.name.rstrip(' ').ljust(7, '\xFF')


@directory.register
class RH5RV2(TYTTHUVF8_V2):
    """Driver for the Rugged RH5R V2."""

    VENDOR = 'Rugged'
    MODEL = 'RH5R-V2'
    _FILEID = b'RUGGED \xFF'
