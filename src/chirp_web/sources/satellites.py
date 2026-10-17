"""AMSAT and SatNOGS satellite-transmitter query sources."""

import logging
import re
from urllib.parse import urlsplit

import requests

from chirp_web import chirp_common, errors
from chirp_web.sources import base

LOG = logging.getLogger(__name__)
AMSAT_URL = (
    'https://raw.githubusercontent.com/palewire/'
    'amateur-satellite-database/main/data/amsat-active-frequencies.json')
SATNOGS_SATELLITES_URL = (
    'https://db.satnogs.org/api/satellites/?status=alive')
SATNOGS_TRANSMITTERS_URL = (
    'https://db.satnogs.org/api/transmitters/?alive=True&status=active')


def _frequency(value):
    """Parse the first frequency from a satellite frequency descriptor."""
    if not value:
        return 0
    match = re.search(r'\d+(?:\.\d+)?', str(value).replace(',', ' '))
    if not match:
        return 0
    try:
        return chirp_common.parse_freq(match.group())
    except errors.InvalidDataError:
        return 0


class AmateurSatellites(base.NetworkResultRadio):
    """Load active satellite downlinks from the AMSAT community database."""

    VENDOR = 'Amateur Satellite'
    MODEL = 'Frequencies'

    def get_label(self):
        return 'AMSAT active frequencies'

    def do_fetch(self, status, params):
        status.send_status('Downloading AMSAT satellite data', 10)
        try:
            response = requests.get(AMSAT_URL, headers=base.HEADERS,
                                   timeout=30)
            response.raise_for_status()
            entries = response.json()
        except (requests.exceptions.RequestException, ValueError) as exc:
            LOG.warning('AMSAT database query failed: %s', exc)
            status.send_fail('Unable to download AMSAT satellite data.')
            return
        if not isinstance(entries, list):
            status.send_fail('AMSAT returned an unexpected data format.')
            return
        for item in entries:
            if not isinstance(item, dict):
                continue
            frequency = _frequency(item.get('downlink'))
            if not frequency:
                continue
            memory = chirp_common.Memory()
            memory.name = str(item.get('name') or 'Satellite')[:16]
            memory.freq = frequency
            uplink = _frequency(item.get('uplink'))
            if uplink:
                chirp_common.split_to_offset(memory, frequency, uplink)
            mode = str(item.get('mode') or '').upper()
            if 'SSB' in mode or 'LINEAR' in mode:
                memory.mode = 'USB'
            elif 'CW' in mode:
                memory.mode = 'CW'
            else:
                memory.mode = 'FM'
            memory.comment = f"Mode: {item.get('mode') or 'Unknown'}"
            self._memories.append(memory)
        if not self._memories:
            status.send_fail('No valid AMSAT satellite frequencies found.')
            return
        for number, memory in enumerate(self._memories):
            memory.number = number
        status.send_end()


class SatNOGS(base.NetworkResultRadio):
    """Load active satellite transmitters from the SatNOGS public API."""

    VENDOR = 'SatNOGS'
    MODEL = 'Transmitters'

    def get_label(self):
        return 'SatNOGS'

    @staticmethod
    def _fetch_all(url):
        results = []
        next_url = url
        page_count = 0
        while next_url:
            page_count += 1
            if page_count > 100:
                raise ValueError('SatNOGS pagination exceeded 100 pages.')
            parsed = urlsplit(next_url)
            if (parsed.scheme != 'https' or
                    parsed.hostname != 'db.satnogs.org'):
                raise ValueError('SatNOGS returned an invalid page URL.')
            response = requests.get(next_url, headers=base.HEADERS,
                                    timeout=30)
            response.raise_for_status()
            data = response.json()
            if isinstance(data, dict) and isinstance(data.get('results'), list):
                results.extend(data['results'])
                next_url = data.get('next')
            elif isinstance(data, list):
                results.extend(data)
                next_url = None
            else:
                raise ValueError('SatNOGS returned an unexpected response.')
        return results

    def do_fetch(self, status, params):
        try:
            status.send_status('Downloading SatNOGS satellite catalog', 10)
            satellites = self._fetch_all(SATNOGS_SATELLITES_URL)
            status.send_status('Downloading SatNOGS transmitters', 55)
            transmitters = self._fetch_all(SATNOGS_TRANSMITTERS_URL)
        except (requests.exceptions.RequestException, ValueError) as exc:
            LOG.warning('SatNOGS query failed: %s', exc)
            status.send_fail('Unable to download SatNOGS data.')
            return

        satellite_by_id = {
            item.get('sat_id'): item for item in satellites
            if isinstance(item, dict)
        }
        mode_filters = params.get('modes') or []
        for transmitter in transmitters:
            if not isinstance(transmitter, dict):
                continue
            satellite = satellite_by_id.get(transmitter.get('sat_id'), {})
            downlink = transmitter.get('downlink_low')
            if not downlink:
                continue
            try:
                frequency = int(downlink)
            except (TypeError, ValueError):
                continue
            mode = str(transmitter.get('mode') or '').upper()
            if mode_filters and not any(
                    str(value).upper() in mode for value in mode_filters):
                continue
            memory = chirp_common.Memory()
            name = satellite.get('name') or 'Satellite'
            description = transmitter.get('description') or ''
            memory.name = f'{name} {description}'.strip()[:16]
            memory.freq = frequency
            uplink = transmitter.get('uplink_low')
            if uplink:
                try:
                    chirp_common.split_to_offset(
                            memory, frequency, int(uplink))
                except (TypeError, ValueError):
                    pass
            if mode == 'FMN':
                memory.mode = 'NFM'
            elif mode in chirp_common.MODES:
                memory.mode = mode
            elif 'USB' in mode or 'LINEAR' in mode:
                memory.mode = 'USB'
            elif 'LSB' in mode:
                memory.mode = 'LSB'
            elif 'CW' in mode:
                memory.mode = 'CW'
            elif 'DSB' in mode:
                memory.mode = 'AM'
            elif 'FM' in mode:
                memory.mode = 'FM'
            else:
                memory.mode = 'DIG'
            norad = satellite.get('norad_cat_id', 'Unknown')
            memory.comment = (
                f"Type: {transmitter.get('type', 'Unknown')} "
                f"https://db.satnogs.org/satellite/{norad}")
            self._memories.append(memory)
        if not self._memories:
            status.send_fail('No valid SatNOGS transmitter frequencies found.')
            return
        for number, memory in enumerate(self._memories):
            memory.number = number
        status.send_end()
