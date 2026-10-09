import json
import os
import time
from contextlib import contextmanager


def _lock(stream):
    if os.name == "nt":
        import msvcrt
        if os.fstat(stream.fileno()).st_size == 0:
            stream.write(b"\0")
            stream.flush()
        stream.seek(0)
        msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
    else:
        import fcntl
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)


def _unlock(stream):
    if os.name == "nt":
        import msvcrt
        stream.seek(0)
        msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def read_selection(path):
    try:
        with open(path, encoding="utf-8") as stream:
            return json.load(stream)
    except (OSError, ValueError):
        return None


def write_json(path, data, attempts=20):
    """Atomically replace a shared file; Windows refuses while the other process is reading it."""
    temporary = f"{path}.{os.getpid()}.tmp"
    with open(temporary, "w", encoding="utf-8") as stream:
        json.dump(data, stream)
    for attempt in range(attempts):
        try:
            os.replace(temporary, path)
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(0.005)


@contextmanager
def shared_lock(path):
    with open(path + ".lock", "a+b") as lock_stream:
        _lock(lock_stream)
        try:
            yield
        finally:
            _unlock(lock_stream)


def publish_selection(path, state, *, initial=False):
    """Write one revision; once a chart is confirmed, later choices cannot replace it."""
    with shared_lock(path):
        previous = read_selection(path)
        same_stage = previous is not None and previous.get("stage") == state["stage"]
        if same_stage and (previous.get("kind") == "next" or
                           initial and previous.get("kind") == "select"):
            return previous, False
        revision = previous.get("version", 0) + 1 if previous else 1
        published = dict(state, version=revision)
        temporary = f"{path}.{os.getpid()}.tmp"
        with open(temporary, "w", encoding="utf-8") as stream:
            json.dump(published, stream)
        os.replace(temporary, path)
        return published, True
