"""Launch the local CHIRP Web browser application."""

import argparse
import logging
import threading
import webbrowser

from chirp_web.webui.api import create_app

import uvicorn

LOG = logging.getLogger(__name__)


def main():
    """Run the local web server and open its page in the default browser."""
    parser = argparse.ArgumentParser(description='Run CHIRP Web in a browser.')
    parser.add_argument(
            '--port', type=int, default=8765,
            help='local HTTP port (default: 8765)')
    parser.add_argument(
            '--no-browser', action='store_true',
            help='do not open a browser automatically')
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error('--port must be between 1024 and 65535')

    app = create_app()
    if not args.no_browser:
        url = f'http://127.0.0.1:{args.port}/'
        threading.Timer(1.0, webbrowser.open, args=(url,)).start()

    logging.info('Starting CHIRP Web web interface on 127.0.0.1:%d', args.port)
    uvicorn.run(app, host='127.0.0.1', port=args.port, log_level='info')


if __name__ == '__main__':
    main()
