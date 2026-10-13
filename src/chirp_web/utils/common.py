"""Classes common to all radios."""

# Copyright 2008 Tom Masterson <kd7cyu@gmail.com>
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

# 50 Tones
TONES = (
    67.0, 69.3, 71.9, 74.4, 77.0, 79.7, 82.5,
    85.4, 88.5, 91.5, 94.8, 97.4, 100.0, 103.5,
    107.2, 110.9, 114.8, 118.8, 123.0, 127.3,
    131.8, 136.5, 141.3, 146.2, 151.4, 156.7,
    159.8, 162.2, 165.5, 167.9, 171.3, 173.8,
    177.3, 179.9, 183.5, 186.2, 189.9, 192.8,
    196.6, 199.5, 203.5, 206.5, 210.7, 218.1,
    225.7, 229.1, 233.6, 241.8, 250.3, 254.1,
)

OLD_TONES = tuple(
    tone for tone in TONES
    if tone not in {159.8, 165.5, 171.3, 177.3, 183.5, 189.9, 196.6,
                    199.5, 206.5, 229.1, 254.1}
)


def VALIDTONE(v):
    """Return true if it is a valid tone.

    Parameters:
       v: float holding value of tone to be checked.
    """
    return isinstance(v, float) and 50 < v < 300


# 104 DTCS Codes
DTCS_CODES = (
    23,  25,  26,  31,  32,  36,  43,  47,  51,  53,  54,
    65,  71,  72,  73,  74,  114, 115, 116, 122, 125, 131,
    132, 134, 143, 145, 152, 155, 156, 162, 165, 172, 174,
    205, 212, 223, 225, 226, 243, 244, 245, 246, 251, 252,
    255, 261, 263, 265, 266, 271, 274, 306, 311, 315, 325,
    331, 332, 343, 346, 351, 356, 364, 365, 371, 411, 412,
    413, 423, 431, 432, 445, 446, 452, 454, 455, 462, 464,
    465, 466, 503, 506, 516, 523, 526, 532, 546, 565, 606,
    612, 624, 627, 631, 632, 654, 662, 664, 703, 712, 723,
    731, 732, 734, 743, 754,
)

# 512 Possible DTCS Codes
ALL_DTCS_CODES = tuple(
    (a * 100) + (b * 10) + c
    for a in range(8)
    for b in range(8)
    for c in range(8)
)

CROSS_MODES = (
    'Tone->Tone',
    'DTCS->',
    '->DTCS',
    'Tone->DTCS',
    'DTCS->Tone',
    '->Tone',
    'DTCS->DTCS',
    'Tone->'
)

# This is the "master" list of modes, and in general things should not be
# added here without significant consideration. These must remain stable and
# universal to allow importing memories between different radio vendors and
# models.
MODES = ('WFM', 'FM', 'NFM', 'AM', 'NAM', 'DV', 'USB', 'LSB', 'CW', 'RTTY',
         'DIG', 'PKT', 'NCW', 'NCWR', 'CWR', 'P25', 'Auto', 'RTTYR',
         'FSK', 'FSKR', 'DMR', 'DN')

TONE_MODES = (
    '',
    'Tone',
    'TSQL',
    'DTCS',
    'DTCS-R',
    'TSQL-R',
    'Cross',
)

TUNING_STEPS = (
    5.0, 6.25, 10.0, 12.5, 15.0, 20.0, 25.0, 30.0, 50.0, 100.0,
    125.0, 200.0,
    # Need to fix drivers using this list as an index!
    9.0, 1.0, 2.5,
)

# These are the default for RadioFeatures.valid_tuning_steps
COMMON_TUNING_STEPS = (5.0, 10.0, 15.0, 20.0, 25.0, 30.0, 50.0, 100.0)

SKIP_VALUES = ('', 'S', 'P')

CHARSET_UPPER_NUMERIC = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ 1234567890'
CHARSET_ALPHANUMERIC = \
    'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz 1234567890'
CHARSET_ASCII = ''.join([chr(x) for x in range(ord(' '), ord('~') + 1)])
CHARSET_1252 = bytes(
    [x for x in range(0x20, 0x100)
     if x not in [0x7F, 0x81, 0x8D, 0x8F, 0x90, 0x9D, 0xA0, 0xAD]]
).decode('cp1252')

# http://aprs.org/aprs11/SSIDs.txt
APRS_SSID = (
    '0 Your primary station usually fixed and message capable',
    '1 generic additional station, digi, mobile, wx, etc',
    '2 generic additional station, digi, mobile, wx, etc',
    '3 generic additional station, digi, mobile, wx, etc',
    '4 generic additional station, digi, mobile, wx, etc',
    "5 Other networks (Dstar, Iphones, Androids, Blackberry's etc)",
    '6 Special activity, Satellite ops, camping or 6 meters, etc',
    "7 walkie talkies, HT's or other human portable",
    "8 boats, sailboats, RV's or second main mobile",
    '9 Primary Mobile (usually message capable)',
    '10 internet, Igates, echolink, winlink, AVRS, APRN, etc',
    '11 balloons, aircraft, spacecraft, etc',
    '12 APRStt, DTMF, RFID, devices, one-way trackers*, etc',
    '13 Weather stations',
    '14 Truckers or generally full time drivers',
    '15 generic additional station, digi, mobile, wx, etc')
APRS_POSITION_COMMENT = (
    'off duty', 'en route', 'in service', 'returning', 'committed',
    'special', 'priority', 'custom 0', 'custom 1', 'custom 2', 'custom 3',
    'custom 4', 'custom 5', 'custom 6', 'EMERGENCY')
# http://aprs.org/symbols/symbolsX.txt
APRS_SYMBOLS = (
    'Police/Sheriff', '[reserved]', 'Digi', 'Phone', 'DX Cluster',
    'HF Gateway', 'Small Aircraft', 'Mobile Satellite Groundstation',
    'Wheelchair', 'Snowmobile', 'Red Cross', 'Boy Scouts', 'House QTH (VHF)',
    'X', 'Red Dot', '0 in Circle', '1 in Circle', '2 in Circle',
    '3 in Circle', '4 in Circle', '5 in Circle', '6 in Circle', '7 in Circle',
    '8 in Circle', '9 in Circle', 'Fire', 'Campground', 'Motorcycle',
    'Railroad Engine', 'Car', 'File Server', 'Hurricane Future Prediction',
    'Aid Station', 'BBS or PBBS', 'Canoe', '[reserved]', 'Eyeball',
    'Tractor/Farm Vehicle', 'Grid Square', 'Hotel', 'TCP/IP', '[reserved]',
    'School', 'PC User', 'MacAPRS', 'NTS Station', 'Balloon', 'Police', 'TBD',
    'Recreational Vehicle', 'Space Shuttle', 'SSTV', 'Bus', 'ATV',
    'National WX Service Site', 'Helicopter', 'Yacht/Sail Boat', 'WinAPRS',
    'Human/Person', 'Triangle', 'Mail/Postoffice', 'Large Aircraft',
    'WX Station', 'Dish Antenna', 'Ambulance', 'Bicycle',
    'Incident Command Post', 'Dual Garage/Fire Dept', 'Horse/Equestrian',
    'Fire Truck', 'Glider', 'Hospital', 'IOTA', 'Jeep', 'Truck', 'Laptop',
    'Mic-Repeater', 'Node', 'Emergency Operations Center', 'Rover (dog)',
    'Grid Square above 128m', 'Repeater', 'Ship/Power Boat', 'Truck Stop',
    'Truck (18 wheeler)', 'Van', 'Water Station', 'X-APRS', 'Yagi at QTH',
    'TDB', '[reserved]'
)


def parse_freq(freqstr: str) -> int:
    """Parse a frequency string and return the value in integral Hz."""
    freqstr = freqstr.strip()
    if not freqstr:
        return 0
    if freqstr.endswith(' MHz'):
        freqstr = freqstr[:-4]
    elif freqstr.endswith(' kHz'):
        return int(freqstr[:-4]) * 1000

    mhz, separator, fractional = freqstr.partition('.')
    if not separator:
        return int(mhz) * 1000000
    if not mhz:
        mhz = '0'
    if len(fractional) > 6:
        raise ValueError(f'Invalid kHz value: {fractional}')

    return (int(mhz) * 1000000) + int(fractional.ljust(6, '0'))


def format_freq(freq: int) -> str:
    """Format a frequency given in Hz as a string."""
    sign = '-' if freq < 0 else ''
    mhz, hz = divmod(abs(freq), 1000000)
    return f'{sign}{mhz}.{hz:06d}'
