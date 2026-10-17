"""mapy73.pl repeater database query source."""

import logging

import requests

from chirp_web import errors
from chirp_web.drivers import generic_csv
from chirp_web.sources import base

LOG = logging.getLogger(__name__)
BASE_URL = 'https://cache.mapy73.pl/snapshot/repeaters/export/chirp/'


class Mapy73Pl(base.NetworkResultRadio):
    """Read a published mapy73.pl CHIRP CSV snapshot."""

    VENDOR = 'mapy73.pl'

    def get_label(self):
        return 'mapy73.pl'

    def do_fetch(self, status, params):
        option = params.get('api_option', '')
        if not isinstance(option, str) or '/' in option or '..' in option:
            status.send_fail('Invalid mapy73.pl region.')
            return
        status.send_status('Downloading repeater snapshot', 10)
        try:
            response = requests.get(
                    BASE_URL + option, headers=base.HEADERS, timeout=30)
            response.raise_for_status()
            source = generic_csv.CSVRadio(None)
            source._load(line.decode('utf-8-sig')
                         for line in response.iter_lines())
        except requests.exceptions.RequestException as exc:
            LOG.warning('mapy73.pl query failed: %s', exc)
            status.send_fail('Unable to query mapy73.pl.')
            return
        except (errors.InvalidDataError, UnicodeDecodeError, ValueError):
            status.send_fail('mapy73.pl returned invalid CSV data.')
            return
        except Exception:
            LOG.exception('Unable to parse mapy73.pl response')
            status.send_fail('Unable to parse mapy73.pl response.')
            return
        self._memories = [
            source.get_memory(number)
            for number in range(len(source.memories))
            if not source.get_memory(number).empty
        ]
        self._memories.sort(key=lambda memory: memory.name.casefold())
        for number, memory in enumerate(self._memories):
            memory.number = number
        if not self._memories:
            status.send_fail('No mapy73.pl repeaters found.')
            return
        status.send_end()
