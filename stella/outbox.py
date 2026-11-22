"""Delivers stored events to the sinks (MQTT, webhook) with retries and backoff.

Delivery is at-least-once: every event carries a unique ``uid`` so consumers
can discard duplicates. Order is kept per sink: on a failure the sink waits
before trying the oldest pending event again.
"""
import logging
import threading

log = logging.getLogger(__name__)

MAX_BACKOFF = 300


def backoff(attempts):
    return min(MAX_BACKOFF, 2 ** min(attempts, 9))


class Outbox:
    def __init__(self, storage, sinks, interval=5.0):
        self.storage = storage
        self.sinks = {s.name: s for s in sinks}
        self.interval = interval
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread = None

    def enabled_sinks(self):
        return [name for name, sink in self.sinks.items() if sink.enabled()]

    def enqueue(self, event):
        event_id = self.storage.add_event(event, self.enabled_sinks())
        self._wake.set()
        return event_id

    def flush_once(self):
        """Try to deliver everything that is due. Returns the number delivered."""
        delivered = 0
        for name, sink in self.sinks.items():
            if not sink.enabled() or not sink.ready():
                continue
            for event_id, event, attempts in self.storage.pending(name):
                try:
                    sink.send(event)
                except Exception as exc:
                    delay = backoff(attempts)
                    log.warning("Delivery to %s failed (event %s, retry in %ss): %s",
                                name, event.get("uid"), delay, exc)
                    self.storage.mark_failed(event_id, name, exc, delay)
                    break
                self.storage.mark_delivered(event_id, name)
                delivered += 1
        return delivered

    def wake(self):
        self._wake.set()

    def start(self):
        self._thread = threading.Thread(target=self._run, name="outbox", daemon=True)
        self._thread.start()
        return self

    def stop(self):
        self._stop.set()
        self._wake.set()
        if self._thread:
            self._thread.join(5)

    def _run(self):
        while not self._stop.is_set():
            self._wake.wait(self.interval)
            self._wake.clear()
            try:
                self.flush_once()
            except Exception:
                log.exception("Outbox iteration failed")
