"""In-memory ring buffer of recent log lines for the web UI."""
import collections
import logging
import threading


class LogBuffer(logging.Handler):
    def __init__(self, capacity=400):
        super().__init__()
        self._lines = collections.deque(maxlen=capacity)
        self._lock_buf = threading.Lock()
        self.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s",
                                            "%Y-%m-%d %H:%M:%S"))

    def emit(self, record):
        try:
            line = self.format(record)
        except Exception:
            return
        with self._lock_buf:
            self._lines.append(line)

    def lines(self, limit=200):
        with self._lock_buf:
            return list(self._lines)[-int(limit):]
