# Copilot instructions for CHIRPQt

## Project context

This repository is a local browser-based reimplementation of CHIRP using the same underlying radio-driver abstractions as the desktop app, but exposing them through a FastAPI backend and a lightweight frontend. The source of truth is in `src/chirpQt`; the web layer is a client that manages local sessions and radio transfers rather than implementing radio logic itself.

## Build, test, and lint

Use `.venv` when present:

- Activate it with: `. .venv/bin/activate`
- Install runtime and test dependencies: `python -m pip install -r requirements.txt -r test-requirements.txt`
- Install the package in editable mode for the local web UI: `python -m pip install -e .`
- Run the full test suite: `pytest`
- Run a single test file: `pytest src/tests/unit/webui/test_api.py -q`
- Run one selected test: `pytest src/tests/unit/webui/test_api.py -k test_open_edit_and_save_csv_image -q`
- Run configured repo hooks: `pre-commit run --all-files`
- Run the legacy style checker against changed files or directories: `python src/tools/cpep8.py <path-or-dir>`

Start the local browser UI after editable install with:

- `chirpqt-web`

This binds to `http://127.0.0.1:8765` and is intended for local use only.

## High-level architecture

- `pyproject.toml` defines the Python package and the `chirpqt-web` console script.
- `src/chirpQt/directory.py` imports driver modules at runtime; their import-time registration populates `DRV_TO_RADIO` and `RADIO_TO_DRV`.
- `src/chirpQt/drivers/` contains model-specific radio drivers. They follow the shared CHIRP interfaces and identify hardware via metadata such as `VENDOR`, `MODEL`, and `VARIANT`.
- `src/chirpQt/chirp_common.py` contains the shared abstractions used across drivers: radio classes, memory layouts, feature validation, file-based image parsing, and clone-mode logic.
- `src/chirpQt/webui/api.py` is the FastAPI layer. It enforces loopback-only host/origin checks and exposes endpoints for opening images, saving memories, and managing radio clone transfers.
- `src/chirpQt/webui/service.py` owns the in-process radio session and transfer manager, which are the coordination points for file parsing, validation, and serial operations.
- `src/chirpQt/webui/static/` contains the frontend assets; it is not an independent radio backend.

## Repository-specific conventions

- Follow nearby driver implementations and existing CHIRP interfaces when adding or changing radio support. Driver registration is an import side effect, not a manually maintained registry.
- Treat `RadioFeatures` and each driver's validation rules as the contract for editable memory fields and values. A field supported by one model is not necessarily valid for another.
- Preserve the local-only security model: the web service is single-user and bound to loopback. Host/origin checks and explicit confirmation before overwriting an unsaved image or writing to a radio are intentional safeguards and should not be relaxed casually.
- Web API tests use FastAPI's `TestClient` and CSV-backed images, so they run without radio hardware. Transfer tests may fake serial devices, but real clone operations require a compatible radio and serial interface.
- The browser interface works with local radio images and CSV channel lists; it is experimental and is not intended for networked or hosted deployment.
- Radio image processing stays local; the app is not designed to upload radio data to a remote service.

## Notes for future Copilot sessions

When making changes, prefer the existing CHIRP abstractions over adding repository-specific shims or duplicated validation logic. If a feature touches the web API, check the corresponding service layer and local-only security checks together; if it touches radio support, keep it consistent with similar drivers and the metadata-driven registration flow.
