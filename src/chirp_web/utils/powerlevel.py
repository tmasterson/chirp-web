"""Classes related to power levels."""

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


import logging
import math
import re

LOG = logging.getLogger(__name__)
_POWER_RE = re.compile(r'\s*([0-9.]+)\s*([Ww]?)\s*')


class PowerLevel:
    """Represents a power level supported by a radio."""

    _label: str
    _power: float

    def __init__(self, label: str, watts: float = 0, dbm: float = 0) -> None:
        """Initialize class.

           Converts wats to dbm.

           Note: If both watts and dbm are provided watts will take
                 precedence.

        Parameters:
           Label: String definin power level.
           wats: power level in wiatts.
           dbm: Power level in dbm.

        Returns: None
        """
        if watts:
            dbm = self.watts_to_dbm(watts)
        self._power = float(dbm)
        self._label = label

    def watts_to_dbm(self, watts: float) -> float:
        """Convert @watts in watts to dbm."""
        return 10 * math.log10(watts) + 30

    def dbm_to_watts(self, dbm: float) -> float:
        """Convert @dbm from dbm to watts."""
        return round(math.pow(10, dbm / 10) / 1000, 1)

    def __str__(self) -> str:
        """Return the label as a string."""
        return str(self._label)

    def __int__(self) -> int:
        """Return the power as an iteger."""
        return int(self._power)

    def __float__(self) -> float:
        """Return power as a float.

        This should already be a float as defined in __init__.
        """
        return self._power

    def __sub__(self, val: float) -> float:
        """Subtract one power level from another."""
        return float(self) - float(val)

    def __add__(self, val: float) -> float:
        """Add 2 power leverls."""
        return float(self) + float(val)

    def __eq__(self, val: object) -> bool:
        """Test if 2 power levels are equal."""
        if not isinstance(val, PowerLevel):
            return NotImplemented
        return float(self) == float(val)

    def __lt__(self, val: object) -> bool:
        """Test if one level is lt this level."""
        if not isinstance(val, PowerLevel):
            return NotImplemented
        return float(self) < float(val)

    def __gt__(self, val: object) -> bool:
        """Test if val is greater that current level."""
        if not isinstance(val, PowerLevel):
            return NotImplemented
        return float(self) > float(val)

    def __bool__(self) -> bool:
        """Test is power level is true."""
        return int(self) != 0

    def __repr__(self) -> str:
        """Stringify entire class."""
        return f'{self._label} ({int(self._power)} dbm)'

    @classmethod
    def parse_power(cls, powerstr: str) -> 'PowerLevel':
        """Parse a power level."""
        match = _POWER_RE.fullmatch(powerstr)
        if not match:
            raise ValueError('Invalid power specification: %r' % powerstr)
        watts = float(match.group(1))
        if watts >= 10:
            formattedlabel = f'{int(watts)}W'
        else:
            formattedlabel = f'{watts:.1f}W'
        return cls(formattedlabel, watts=watts)
