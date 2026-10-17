# Copilot instructions for CHIRP Web

## Project context

This repository packages the CHIRP radio abstractions and drivers behind an experimental local browser interface. The Python package uses a `src/` layout, with implementation in `src/chirp_web` and tests in `src/tests`. The web UI is a client for existing radio/image operations; it should not duplicate driver or radio logic.

## Build, test, and lint

The project requires Python 3.12 or newer. Use `.venv` when present:

- Activate it with: `. .venv/bin/activate`
- Install runtime and test dependencies: `python -m pip install -r requirements.txt -r test-requirements.txt`
- Install the package in editable mode: `python -m pip install -e .`
- Run the full test suite: `pytest`
- Run a single test file: `pytest src/tests/unit/webui/test_api.py -q`
- Run one selected test: `pytest src/tests/unit/webui/test_api.py::test_open_edit_and_save_csv_image -q`
- Run the installed-package end-to-end test: `pytest src/tests/e2e/test_package.py -q`
- Run configured repo hooks: `pre-commit run --all-files`
- Run the legacy style checker against a changed file or directory: `python src/tools/cpep8.py <path-or-dir>` (the configured hook excludes `src/chirp_web/drivers/`)

Start the local browser UI after editable install with `chirp-web` (or `python -m chirp_web.webui.main`). It binds to `http://127.0.0.1:8765`; the CLI also accepts `--port` and `--no-browser`.

## High-level architecture

- `pyproject.toml` defines the Python package and the `chirp-web` console script.
- `src/chirp_web/chirp_common.py` defines shared radio, memory, feature-validation, file-image, and clone-mode abstractions. Model-specific drivers in `src/chirp_web/drivers/` implement these contracts.
- `src/chirp_web/directory.py` loads driver modules; their import-time registration builds the driver lookup maps and makes the drivers available for image detection and radio selection.
- `src/chirp_web/webui/main.py` starts the app, while `api.py` defines the FastAPI routes, request models, and local request guards. `service.py` owns the single in-process image/radio session and coordinates validation, file operations, and serial transfers.
- `src/chirp_web/webui/static/` contains the browser client served by the same process. The UI also queries supported external repeater-data sources; radio images and clone operations remain local.
- Unit tests exercise drivers, shared abstractions, utilities, and the API. The web API tests use CSV-backed images and faked radios; `src/tests/e2e/test_package.py` launches the actual package entry point and tests it over HTTP.

## Repository-specific conventions

- Follow nearby driver implementations and existing CHIRP interfaces when adding or changing radio support. Driver registration is an import side effect, not a manually maintained registry.
- Treat `RadioFeatures` and each driver's validation rules as the contract for editable memory fields and values. A field supported by one model is not necessarily valid for another.
- Web API request models reject unknown fields and apply strict constraints. For API behavior changes, keep the request model, route, and service behavior aligned.
- Preserve the local-only security model: the server binds to loopback, checks host/origin, and requires confirmation for discarding unsaved work or writing to a radio. Do not make it network-facing without addressing authentication and local-device security.
- Keep hardware-independent tests independent of physical radios by using CSV-backed images or fake radios. Actual clone transfers require a compatible radio and serial interface.
- Follow repository guidance in `README.md` and `.github/pull_request_template.md` when preparing contributions.
