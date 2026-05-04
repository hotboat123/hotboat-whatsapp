"""Shared in-memory log buffer — imported by main.py and admin_router.py."""
import collections
import logging

log_buffer: collections.deque = collections.deque(maxlen=500)


class _BufferHandler(logging.Handler):
    def emit(self, record: logging.LogRecord):
        try:
            log_buffer.append({
                "ts":      self.formatTime(record, "%Y-%m-%d %H:%M:%S"),
                "level":   record.levelname,
                "logger":  record.name,
                "message": record.getMessage(),
            })
        except Exception:
            pass


def install():
    """Attach the buffer handler to the root logger (idempotent)."""
    root = logging.getLogger()
    if not any(isinstance(h, _BufferHandler) for h in root.handlers):
        h = _BufferHandler()
        h.setLevel(logging.DEBUG)
        root.addHandler(h)
