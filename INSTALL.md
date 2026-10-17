# Installing CHIRP Web

CHIRP Web requires Python 3.12 or newer. It is currently distributed from its
source repository; install it by cloning the repository and installing it with
`pip`. The commands below install the application and its runtime dependencies
into a virtual environment.

## Windows

1. Install Python 3.12 or newer from [python.org](https://www.python.org/downloads/)
   and Git for Windows. During Python setup, enable the Python launcher (`py`).
2. Open PowerShell and clone the repository:

   ```powershell
   git clone https://github.com/tmasterson/chirp-web.git
   cd chirp-web
   ```

3. Create and activate a virtual environment, then install the package:

   ```powershell
   py -3.12 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install --upgrade pip
   python -m pip install .
   ```

   Windows-specific dependencies are installed automatically.
4. Start the application:

   ```powershell
   chirp-web
   ```

   Open [http://127.0.0.1:8765](http://127.0.0.1:8765) if a browser does not
   open automatically. To stop the server, press **Ctrl+C** in PowerShell.

## Linux

1. Install Git and Python 3.12 or newer, including its `venv` support. On
   Debian or Ubuntu releases that provide Python 3.12 packages, for example:

   ```sh
   sudo apt update
   sudo apt install git python3.12 python3.12-venv
   ```

   On other distributions, use the distribution's package manager or Python
   installation instructions to install Python 3.12+ and its venv module.
2. Clone the repository and enter its directory:

   ```sh
   git clone https://github.com/tmasterson/chirp-web.git
   cd chirp-web
   ```

3. Create and activate a virtual environment, then install the package:

   ```sh
   python3.12 -m venv .venv
   . .venv/bin/activate
   python -m pip install --upgrade pip
   python -m pip install .
   ```
4. Start the application:

   ```sh
   chirp-web
   ```

   Open [http://127.0.0.1:8765](http://127.0.0.1:8765) if a browser does not
   open automatically. To stop the server, press **Ctrl+C** in the terminal.

## Using a radio on Linux

The web application can open and edit supported radio image files without a
connected radio. To communicate with a radio, connect its programming cable
and ensure your user has permission to access its serial device. On many
Debian/Ubuntu systems, serial devices are accessible to members of the
`dialout` group:

```sh
sudo usermod -aG dialout "$USER"
```

Sign out and back in for the group change to take effect. Device names and
permissions vary by distribution and cable.

## Notes

- Keep the virtual environment activated whenever you run `chirp-web`. If you
  open a new terminal, go to the cloned directory and activate it again.
- To update an existing clone, run `git pull` and then
  `python -m pip install .` again from that directory, with the environment
  activated.
- The server listens only on `127.0.0.1` and is intended for local use. Review
  the selected image before writing it to a radio; writing replaces the radio's
  current programming.
