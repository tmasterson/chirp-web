"""thee custom errors that can be thrown by this application."""

# Copyright 2025 Tom Masterson <kd7cyu@gmail.com>
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

import enum


class Reasons(enum.Enum):
    """Look at removing this calss."""

    NO_CONNECTION_K1 = 'No response from radio. Check connector and cabling!'


class InvalidDataError(Exception):
    """The radio driver encountered some invalid data."""


class InvalidValueError(Exception):
    """An invalid value for a given parameter was used."""


class InvalidMemoryLocation(Exception):
    """The requested memory location does not exist."""


class RadioError(Exception):
    """An error occurred while talking to the radio."""


class UnsupportedToneError(Exception):
    """The radio does not support the specified tone value."""


class ImageDetectFailed(Exception):
    """The driver for the supplied image could not be determined."""


class ImageMetadataInvalidModel(Exception):
    """The image contains metadata but no suitable driver is found."""


class ImmutableValueError(ValueError):
    """Error class not currently used."""


class SpecificRadioError(RadioError):
    """An error with a specific reason and troubleshooting reference."""

    CODE: None | Reasons = None

    def __init__(self, msg=None):
        """Initialize error."""
        if self.CODE not in Reasons:
            raise RuntimeError('Invalid reason; '
                               'must be one of chirp_web.errors.Reasons')
        super().__init__(msg or self.CODE.value)

    def get_link(self):
        """Return a link to the wiki."""
        return ('https://chirpmyradio.com/projects/chirp/wiki/'
                'Error-%s' % self.CODE.name)


class RadioNoContactLikelyK1(SpecificRadioError):
    """A radio that uses a K1 connector likely to have fitment issues."""

    CODE = Reasons.NO_CONNECTION_K1


class ValidationMessage(Exception):
    """Base class for Validation Errors and Warnings."""


class ValidationWarning(ValidationMessage):
    """A non-fatal warning during memory validation."""


class ValidationError(ValidationMessage):
    """A fatal error during memory validation."""
