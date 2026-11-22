"""Daily entry/exit totals and current occupancy, persisted in SQLite."""
import datetime
import threading

KEY = "counters"


def business_day(now, reset_time):
    """Date the counters belong to: the day starts at ``reset_time`` (HH:MM)."""
    hh, mm = (int(x) for x in reset_time.split(":"))
    return (now - datetime.timedelta(hours=hh, minutes=mm)).date().isoformat()


class Counters:
    def __init__(self, storage, config, clock=None):
        self.storage = storage
        self.config = config
        self._clock = clock or datetime.datetime.now
        self._lock = threading.Lock()
        saved = storage.get(KEY) or {}
        self._state = {
            "day": saved.get("day") or self._today(),
            "in": int(saved.get("in", 0)),
            "out": int(saved.get("out", 0)),
            "occupancy": int(saved.get("occupancy", 0)),
        }
        self.check_rollover()

    def _today(self):
        return business_day(self._clock(), self.config.get("counting.reset_time", "00:00"))

    def _save(self):
        self.storage.set(KEY, self._state)

    def check_rollover(self):
        """Reset the daily totals when the business day changes. Returns True if reset."""
        today = self._today()
        with self._lock:
            if self._state["day"] == today:
                return False
            self._state = {"day": today, "in": 0, "out": 0, "occupancy": 0}
            self._save()
            return True

    def apply(self, direction):
        self.check_rollover()
        with self._lock:
            if direction == "in":
                self._state["in"] += 1
                self._state["occupancy"] += 1
            else:
                self._state["out"] += 1
                self._state["occupancy"] = max(0, self._state["occupancy"] - 1)
            self._save()
        return self.state()

    def reset(self, occupancy=0):
        with self._lock:
            self._state = {"day": self._today(), "in": 0, "out": 0, "occupancy": max(0, int(occupancy))}
            self._save()
        return self.state()

    def state(self):
        limit = int(self.config.get("counting.occupancy_limit", 0) or 0)
        with self._lock:
            state = dict(self._state)
        state["limit"] = limit
        state["full"] = bool(limit) and state["occupancy"] >= limit
        return state
