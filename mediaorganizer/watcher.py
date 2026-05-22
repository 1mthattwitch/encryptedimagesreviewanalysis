"""
Watch-folder mode: auto-process new files as they appear.
Uses watchdog library (optional dep).
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional


def is_available() -> bool:
    try:
        import watchdog  # noqa
        return True
    except ImportError:
        return False


class FolderWatcher:
    """
    Watch a folder for new files. Calls callback(path: Path) for each new file.
    Usage:
        w = FolderWatcher(folder, callback)
        w.start()
        ...
        w.stop()
    """

    def __init__(self, folder: Path, callback: Callable[[Path], None]):
        self.folder = folder
        self.callback = callback
        self._observer = None

    def start(self) -> None:
        try:
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler

            watcher = self

            class _Handler(FileSystemEventHandler):
                def on_created(self, event):
                    if not event.is_directory:
                        watcher.callback(Path(event.src_path))

            self._observer = Observer()
            self._observer.schedule(_Handler(), str(self.folder), recursive=True)
            self._observer.start()
        except ImportError:
            raise ImportError(
                "watchdog not installed. Run: pip install watchdog"
            )

    def stop(self) -> None:
        if self._observer:
            self._observer.stop()
            self._observer.join()
            self._observer = None

    @property
    def is_running(self) -> bool:
        return self._observer is not None and self._observer.is_alive()
