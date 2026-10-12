"""Helpers shared by clone-mode radio drivers."""

from chirpQt import errors


def exit_programming_mode(radio):
    """Tell a radio to exit programming mode."""
    try:
        radio.pipe.write(b"E")
    except Exception:
        raise errors.RadioError("Radio refused to exit programming mode")
