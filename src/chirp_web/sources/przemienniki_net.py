# Copyright 2023 Dan Smith <chirp@f.danplanet.com>
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

import logging
from gettext import gettext as _

import requests

from chirp_web.drivers import generic_csv
from chirp_web import errors
from chirp_web.sources import base

LOG = logging.getLogger(__name__)


class PrzemiennikiNet(base.NetworkResultRadio):
    VENDOR = 'przemienniki.net'

    def get_label(self):
        return 'przemienniki.net'

    def do_fetch(self, status, params):
        status.send_status(_('Querying'), 10)
        params = params.copy()
        search_range = params.get('range')
        if not search_range or int(search_range) == 0:
            params.pop('range', None)
        LOG.debug('query params: %s', params)
        self._memories = []
        try:
            r = requests.get('http://przemienniki.net/export/chirp_web.csv',
                             headers=base.HEADERS,
                             params=params,
                             stream=True)
            r.raise_for_status()
        except requests.exceptions.RequestException as e:
            LOG.error('Failed to query przemienniki.net: %s' % e)
            status.send_fail(_('Unable to query'))
            return
        status.send_status(_('Parsing'), 20)
        try:
            csv = generic_csv.CSVRadio(None)
            csv._load(x.decode() for x in r.iter_lines())
        except errors.InvalidDataError:
            status.send_fail(_('No results'))
            return
        except Exception as e:
            LOG.error('Error parsing result: %s' % e)
            status.send_fail(_('Failed to parse result'))
            return

        status.send_status(_('Sorting'), 80)

        self._memories = [memory for number in range(1, 999)
                          if not (memory := csv.get_memory(number)).empty]
        if not any((params.get('latitude'), params.get('longitude'))):
            LOG.debug('Sorting memories by name')
            self._memories.sort(key=lambda m: m.name)
            # Now renumber them
            for i, mem in enumerate(self._memories):
                mem.number = i + 1

        return status.send_end()
