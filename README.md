# CHIRP Project

This is the official git repository for the
__[CHIRP](https://www.chirpmyradio.com)__ project.

When submitting PRs, please see [this file](.github/pull_request_template.md)
for rules and guidelines.

## Local web interface

CHIRP Web includes an experimental browser interface backed by the existing
Python radio drivers. Install the project and run:

```sh
python -m pip install -e .
chirp-web
```

The app opens at `http://127.0.0.1:8765`. It can open supported radio image
files and CSV channel lists, edit and save channels, and read/write clone-mode
radios through a serial port detected on the same computer. Use **Write to
radio** only after reviewing the selected image and confirming the operation;
it replaces the radio's current programming.

The web server binds to loopback and is not intended for LAN or hosted use.
Radio images are processed locally and are not uploaded to a remote service.

For platform-specific installation instructions, see
[Installing CHIRP Web](INSTALL.md).
