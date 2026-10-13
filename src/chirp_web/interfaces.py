"""Holds all interfaces for the projecjt."""

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

import abc


class MappingModelIndexInterface(metaclass=abc.ABCMeta):
    """Interface for mappings with index capabilities."""

    def __subclasshook__(cls, subclass):
        """Test to see if the class implements this interface."""
        return (hasattr(subclass, 'get_index_bounds') and
                callable(subclass.get_index_bounds) and
                hasattr(subclass, 'get_memory_index') and
                callable(subclass.get_memory_index) and
                hasattr(subclass, 'set_memory_index') and
                callable(subclass.set_memory_index) and
                hasattr(subclass, 'get_next_mapping_index') and
                callable(subclass.get_next_mapping_index) or
                NotImplemented)

    @abc.abstractmethod
    def get_index_bounds(self):
        """Return a tuple (lo,hi) of the min and max mapping indices."""
        raise NotImplementedError()

    @abc.abstractmethod
    def get_memory_index(self, memory, mapping):
        """Return the index of @memory in @mapping."""
        raise NotImplementedError()

    @abc.abstractmethod
    def set_memory_index(self, memory, mapping, index):
        """Set the index of @memory in @mapping to @index."""
        raise NotImplementedError()

    @abc.abstractmethod
    def get_next_mapping_index(self, mapping):
        """Return the next available mapping index in @mapping.

        raises Exception if full.
        """
        raise NotImplementedError()


class DetectableInterface:
    """An interface for detectable items."""

    def __subclasshook__(cls, subclass):
        """Test to see if the class implements this interface."""
        return (hasattr(subclass, 'detect_from_serial') and
                callable(subclass.detext_from_serial) and
                hasattr(subclass, 'detected_odels') and
                callable(subclass.detected_models) and
                hasattr(subclass, 'detect_model') or
                NotImplemented)

    @abc.abstractmethod
    def detect_from_serial(cls, pipe):
        """Communicate with the radio via serial to determine proper class.

        Returns an in implementation of CloneModeRadio if detected, or raises
        RadioError if not. If NotImplemented is raised, we assume that no
        detection is possible or necessary.
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def detected_models(cls, include_self=True):
        """Return detected models."""
        raise NotImplementedError()

    @abc.abstractmethod
    def detect_model(cls, detected_cls):
        """Detect models and set proper variables."""
        raise NotImplementedError()
