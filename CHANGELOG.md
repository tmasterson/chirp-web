# Changelog

Notable changes to CHIRP Web are documented here. This project is under active
development and has not yet recorded a versioned release.

## Development history (2026-09-28 to 2026-10-13)

### Added

- Added an experimental local browser interface for working with radio images
  and CSV channel lists, editing and saving channels, and reading from or
  writing to clone-mode radios over a serial connection.
- Added web UI settings.
- Added unit tests for utility modules and optimized utility and core code.

### Changed

- Renamed the package and project to `chirp-web` to reflect its browser-based
  interface.
- Improved code readability and performance across utility and core modules.

### Fixed

- Resolved test and pre-commit failures and cleaned up linting and mypy errors.
- Updated package metadata, entry points, and related files to use the
  `chirp-web` project name.
