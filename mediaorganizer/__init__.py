"""mediaorganizer — offline media scanner, organiser, and AI renamer."""
__version__ = "1.0.0"

import os
import contextlib

os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")
os.environ.setdefault("OPENCV_FFMPEG_LOGLEVEL", "-8")   # AV_LOG_QUIET
os.environ.setdefault("OPENCV_IO_ENABLE_OPENEXR", "0")


@contextlib.contextmanager
def _quiet_stderr():
    """Redirect C-level stderr (fd 2) to devnull for the duration of the block.

    Necessary on Windows where ffmpeg/libav writes directly to the console
    handle, bypassing Python's sys.stderr and process-level redirects.
    """
    try:
        devnull = os.open(os.devnull, os.O_WRONLY)
        saved = os.dup(2)
        os.dup2(devnull, 2)
        os.close(devnull)
    except OSError:
        saved = None
    try:
        yield
    finally:
        if saved is not None:
            os.dup2(saved, 2)
            os.close(saved)
