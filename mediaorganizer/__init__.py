"""mediaorganizer — offline media scanner, organiser, and AI renamer."""
__version__ = "1.0.0"

import os
os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")
os.environ.setdefault("OPENCV_FFMPEG_LOGLEVEL", "quiet")
os.environ.setdefault("OPENCV_IO_ENABLE_OPENEXR", "0")
