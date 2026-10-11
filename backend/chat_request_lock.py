"""Per-process serialization for requests targeting the same chat session.

The booking transaction remains the cross-request safety boundary. This lock
prevents ordinary double-click/Enter duplicates from observing the same
conversation state before the first request advances it.
"""

from contextlib import contextmanager
import threading

_registry_lock = threading.Lock()
_locks: dict[str, threading.RLock] = {}


@contextmanager
def session_request_lock(session_id: str):
    with _registry_lock:
        lock = _locks.setdefault(session_id, threading.RLock())
    with lock:
        yield
