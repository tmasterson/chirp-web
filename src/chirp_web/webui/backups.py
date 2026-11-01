"""Local retained-backup storage for one browser session."""


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


import re
from pathlib import Path


class BackupStorage:
    """Manage optional retained backups outside the active image tab."""

    def __init__(self, error_type):
        self._error_type = error_type
        self.directory: Path | None = None
        self.retention = 10

    def settings(self):
        """Return the configured local retention settings."""
        return {
            'directory': str(self.directory) if self.directory else None,
            'retention': self.retention,
        }

    def configure(self, directory, retention):
        """Validate and apply an explicit retained-backup directory."""
        if directory is None:
            self.directory = None
            return self.settings()
        path = Path(directory).expanduser()
        try:
            path = path.resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise self._error_type(
                    'The backup directory does not exist.', 422) from exc
        if not path.is_dir():
            raise self._error_type(
                    'The backup location must be a directory.', 422)
        self.directory = path
        self.retention = retention
        self.prune()
        return self.settings()

    def retained_paths(self):
        """Return retained backups ordered from oldest to newest."""
        if self.directory is None:
            return []
        try:
            return sorted(
                    (path for path in self.directory.glob('chirp-web-backup-*')
                     if path.is_file()),
                    key=lambda path: path.stat().st_mtime)
        except OSError as exc:
            raise self._error_type(
                    'The retained backup directory is unavailable.',
                    500) from exc

    def prune(self):
        """Remove retained backups beyond the configured limit."""
        paths = self.retained_paths()
        for path in paths[:-self.retention]:
            try:
                path.unlink()
            except OSError as exc:
                raise self._error_type(
                        'An expired retained backup could not be removed.',
                        500) from exc

    def entries(self, temporary_paths, source_name, safe_name):
        """Describe temporary and retained backups without exposing paths."""
        temporary = [{
            'id': Path(path).name,
            'filename': safe_name(source_name),
            'created_at': int(Path(path).stat().st_mtime),
            'persistent': False,
        } for path in temporary_paths if Path(path).exists()]
        retained = [{
            'id': path.name,
            'filename': path.name.split('-', 5)[-1],
            'created_at': int(path.stat().st_mtime),
            'persistent': True,
        } for path in self.retained_paths()]
        return sorted(
                temporary + retained, key=lambda item: item['created_at'])

    def find(self, temporary_paths, backup_id):
        """Return a validated temporary or retained backup path."""
        if not re.fullmatch(r'[A-Za-z0-9._ -]{1,255}', backup_id):
            raise self._error_type('Backup was not found.', 404)
        for path in temporary_paths:
            candidate = Path(path)
            if candidate.name == backup_id and candidate.is_file():
                return candidate
        if self.directory is not None:
            candidate = self.directory / backup_id
            if (candidate.name == backup_id and candidate.is_file() and
                    candidate.parent == self.directory and
                    candidate.name.startswith('chirp-web-backup-')):
                return candidate
        raise self._error_type('Backup was not found.', 404)

    def is_retained(self, path):
        """Return whether a backup path belongs to retained storage."""
        return self.directory is not None and path.parent == self.directory
