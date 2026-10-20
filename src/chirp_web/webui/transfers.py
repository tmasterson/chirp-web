"""Background serial transfer management for the local web UI."""

import logging
import re
import tempfile
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import serial
from serial.tools import list_ports

from chirp_web import chirp_common, directory
from chirp_web.webui.service import DriverSession, RedactedSerialTrace, WebServiceError

LOG = logging.getLogger(__name__)


class TransferManager:
    """Run blocking serial transfers off the web request thread."""

    def __init__(self, session: DriverSession):
        """Create a transfer queue for one active radio session."""
        self.session = session
        self.executor = ThreadPoolExecutor(
                max_workers=1, thread_name_prefix='chirp-web-radio')
        self.lock = threading.Lock()
        self.jobs: dict[str, dict[str, object]] = {}

    @staticmethod
    def radios():
        """Return clone-mode and live-mode radios that support serial I/O."""
        directory.import_drivers()
        result = []
        for ident, radio_class in sorted(directory.DRV_TO_RADIO.items()):
            if not issubclass(
                    radio_class,
                    (chirp_common.CloneModeRadio, chirp_common.LiveRadio)):
                continue
            result.append({
                'id': ident,
                'name': radio_class.get_name(),
                'baud_rate': getattr(radio_class, 'BAUD_RATE', None),
                'mode': ('live' if issubclass(
                    radio_class, chirp_common.LiveRadio) else 'clone'),
            })
        return result

    @staticmethod
    def _prompts(radio_class, operation=None):
        try:
            prompts = radio_class.get_prompts()
        except NameError as exc:
            raise WebServiceError(
                'This radio driver could not provide transfer instructions.',
                500) from exc
        keys = ('info', 'experimental', 'pre_download', 'pre_upload')
        if operation == 'download':
            keys = ('info', 'experimental', 'pre_download')
        elif operation == 'upload':
            keys = ('info', 'experimental', 'pre_upload')
        return {
            key: str(getattr(prompts, key, '') or '').strip()
            for key in keys if getattr(prompts, key, '')
        }

    def prompts(self, radio_id):
        """Return the selected driver's relevant user-facing instructions."""
        try:
            radio_class = directory.get_radio(radio_id)
        except Exception as exc:
            raise WebServiceError('Unknown radio model.', 404) from exc
        return {'download': self._prompts(radio_class, 'download'),
                'upload': self._prompts(radio_class, 'upload')}

    def upload_prompts(self):
        """Return prompt text for the image currently selected for upload."""
        with self.session.lock:
            radio = self.session._tab.radio
            if radio is None:
                raise WebServiceError('Open a radio image before editing.', 409)
            return self._prompts(radio.__class__, 'upload')

    @staticmethod
    def ports():
        """Return serial ports currently detected on this computer."""
        return [{'port': item.device, 'description': item.description}
                for item in list_ports.comports()]

    @staticmethod
    def valid_port(port):
        """Permit detected ports and explicit local serial device names."""
        if '\x00' in port or len(port) > 512:
            return False
        if port in {item['port'] for item in TransferManager.ports()}:
            return True
        return (port.startswith('/dev/') or
                bool(re.fullmatch(r'COM[1-9][0-9]*', port, re.IGNORECASE)))

    def start(self, operation: str, radio_id: str, port: str,
              confirm: bool = False, confirm_replace: bool = False,
              confirm_prompts: bool = False):
        """Validate and queue one upload or download operation."""
        with self.session.lock:
            self.session._ensure_idle()
            if operation == 'upload':
                radio = self.session._tab.radio
                if radio is None:
                    raise WebServiceError(
                            'Open a radio image before editing.', 409)
                if not isinstance(radio, chirp_common.CloneModeRadio):
                    raise WebServiceError(
                            'Upload is available only for clone-mode images.',
                            409)
                if not confirm:
                    raise WebServiceError(
                            'Confirm that you want to write this image to the '
                            'radio.', 400)
                radio_class = radio.__class__
            else:
                try:
                    radio_class = directory.get_radio(radio_id)
                except Exception as exc:
                    raise WebServiceError('Unknown radio model.', 404) from exc
                if not issubclass(
                        radio_class, (chirp_common.CloneModeRadio,
                                      chirp_common.LiveRadio)):
                    raise WebServiceError(
                            'Radio model does not support serial transfers.',
                            422)

            if (self._prompts(radio_class, operation) and
                    not confirm_prompts):
                raise WebServiceError(
                        'Review and confirm this radio’s transfer '
                        'instructions before continuing.', 409)
            if not self.valid_port(port):
                raise WebServiceError(
                        'Select a detected port or provide a local serial '
                        'device path.',
                        422)
            job_id = str(uuid.uuid4())
            job = {
                'id': job_id,
                'operation': operation,
                'state': 'running',
                'progress': 0,
                'message': 'Starting transfer',
                'error': None,
                'cancelled': threading.Event(),
                'pipe': None,
            }
            with self.lock:
                self.jobs[job_id] = job
            if operation == 'download':
                self.session._new_tab()
                job['tab_id'] = self.session.active_tab_id
            self.session.active_job = job_id
            self.executor.submit(
                    self._run, job_id, radio_class, port, operation)
            return self._public(job)

    @staticmethod
    def _public(job):
        return {key: value for key, value in job.items()
                if key not in {'cancelled', 'pipe'}}

    def _set_progress(self, job_id: str, status):
        with self.lock:
            job = self.jobs[job_id]
            if job['cancelled'].is_set():
                return
            maximum = status.max or 1
            job['progress'] = max(0, min(100, int(status.cur * 100 / maximum)))
            job['message'] = str(status.msg)

    def _run(self, job_id: str, radio_class, port: str, operation: str):
        pipe = None
        temp_path = None
        failure = None
        try:
            with self.lock:
                job = self.jobs[job_id]
            if job['cancelled'].is_set():
                raise WebServiceError('Transfer was cancelled.', 409)
            raw_pipe = serial.Serial(port=port, timeout=0.5)
            with self.session.lock:
                pipe = RedactedSerialTrace(
                        raw_pipe, self.session._tab.serial_trace)
            with self.lock:
                self.jobs[job_id]['pipe'] = pipe
            if job['cancelled'].is_set():
                raise WebServiceError('Transfer was cancelled.', 409)
            detected = getattr(radio_class, 'detect_from_serial', None)
            if operation == 'download' and callable(detected):
                try:
                    detected_class = detected(pipe)
                    if (isinstance(detected_class, type) and
                            issubclass(detected_class, radio_class)):
                        radio_class = detected_class
                except Exception:
                    LOG.info('Radio model detection was unavailable',
                             exc_info=True)
            if operation == 'download':
                radio = radio_class(pipe)
            else:
                with self.session.lock:
                    radio = self.session._tab.radio
                    if radio is None:
                        raise WebServiceError(
                                'Open a radio image before editing.', 409)
                    radio.set_pipe(pipe)
            radio.status_fn = lambda status: self._set_progress(
                    job_id, status)
            if operation == 'download':
                if isinstance(radio, chirp_common.LiveRadio):
                    with self.session.lock:
                        self.session._replace_radio(
                                radio, f'{radio_class.get_name()} (live)',
                                None)
                        self.session._tab.live_port = pipe
                    pipe = None
                else:
                    radio.sync_in()
                    handle = tempfile.NamedTemporaryFile(
                            prefix='chirp-web-download-',
                            suffix='.img',
                            delete=False)
                    temp_path = handle.name
                    handle.close()
                    radio.save_mmap(temp_path)
                    with self.session.lock:
                        self.session._replace_radio(
                                radio, f'{radio_class.get_name()}.img',
                                temp_path)
                        temp_path = None
                        try:
                            self.session.create_backup('download')
                        except Exception:
                            LOG.exception('Unable to create download backup')
            else:
                with self.session.lock:
                    try:
                        self.session.create_backup('upload')
                    except Exception:
                        LOG.exception('Unable to create upload backup')
                radio.sync_out()
                with self.session.lock:
                    self.session.dirty = False
        except Exception as exc:
            failure = exc
            if not (isinstance(exc, WebServiceError) and
                    exc.status_code == 409):
                LOG.exception('Radio %s failed', operation)
        finally:
            try:
                if pipe is not None and pipe.is_open:
                    pipe.close()
            except Exception as exc:
                LOG.exception(
                        'Unable to close serial port after %s', operation)
                if failure is None:
                    failure = exc
            if temp_path:
                Path(temp_path).unlink(missing_ok=True)
            with self.session.lock:
                if self.session.active_job == job_id:
                    self.session.active_job = None
                with self.lock:
                    cancelled = self.jobs[job_id]['cancelled'].is_set()
                    self.jobs[job_id]['pipe'] = None
                    if cancelled:
                        self.jobs[job_id].update(
                                state='cancelled', message='Transfer cancelled',
                                error=None)
                    elif failure is None:
                        self.jobs[job_id].update(
                                state='complete', progress=100,
                                message='Transfer done')
                    else:
                        self.jobs[job_id].update(
                                state='failed', error=str(failure),
                                message='Transfer failed')

    def get(self, job_id: str):
        """Return progress for one transfer job."""
        with self.lock:
            job = self.jobs.get(job_id)
            if job is None:
                raise WebServiceError('Transfer job was not found.', 404)
            return self._public(job)

    def cancel(self, job_id: str):
        """Request cancellation by closing the active serial connection."""
        with self.lock:
            job = self.jobs.get(job_id)
            if job is None:
                raise WebServiceError('Transfer job was not found.', 404)
            if job['state'] != 'running':
                return self._public(job)
            job['cancelled'].set()
            job['message'] = 'Cancelling transfer'
            pipe = job.get('pipe')
        if pipe is not None:
            try:
                pipe.close()
            except Exception:
                LOG.exception('Unable to close serial port for cancellation')
        return self._public(job)

    def close(self):
        """Stop accepting transfers and release session resources."""
        self.executor.shutdown(wait=False, cancel_futures=True)
        self.session.close()
