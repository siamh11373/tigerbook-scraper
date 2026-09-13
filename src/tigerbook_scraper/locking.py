import os
from contextlib import contextmanager
from pathlib import Path

from .errors import ConfigurationError


@contextmanager
def run_lock(directory: Path):
    """OS-owned lock is released even if the process crashes. Keep the inode stable."""
    directory.mkdir(parents=True, exist_ok=True)
    handle = (directory / ".run.lock").open("a+b")
    try:
        if os.name == "nt":
            import msvcrt

            if handle.tell() == 0:
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                raise ConfigurationError("Another process is using this run directory.") from None
        else:
            import fcntl

            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                raise ConfigurationError("Another process is using this run directory.") from None
        yield
    finally:
        handle.close()
