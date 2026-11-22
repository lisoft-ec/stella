"""RGB status LED on the Coral board GPIOs (or a no-op driver elsewhere).

Colour = a short flash for each crossing (entry/exit) or else the
highest-priority active condition: error > full > hotspot > no_network.
With nothing to show the LED is off.
"""
import logging
import threading
import time

log = logging.getLogger(__name__)

PRIORITY = ("error", "full", "hotspot", "no_network")
OFF = (0, 0, 0)


class _NullPins:
    def write(self, rgb):
        pass

    def close(self):
        pass


class _GpioPins:
    def __init__(self, pins, active_level):
        from periphery import GPIO

        self.active = int(active_level)
        self.gpios = [GPIO(int(pins[c]), "out") for c in ("red", "green", "blue")]

    def write(self, rgb):
        for gpio, value in zip(self.gpios, rgb):
            gpio.write(bool(value) == bool(self.active))

    def close(self):
        for gpio in self.gpios:
            gpio.close()


class Leds:
    def __init__(self, config):
        self.config = config
        self._lock = threading.Lock()
        self._conditions = set()
        self._flash = None
        self._flash_until = 0.0
        self._current = None
        self._stop = threading.Event()
        self._thread = None
        self._preview = None
        self._preview_until = 0.0
        self.pins = _NullPins()
        self.driver = "none"
        self.reconfigure()

    def reconfigure(self):
        cfg = self.config.section("leds")
        with self._lock:
            self.pins.close()
            self.pins = _NullPins()
            self.driver = "none"
            if cfg["driver"] == "gpio":
                try:
                    self.pins = _GpioPins(cfg["pins"], cfg["active_level"])
                    self.driver = "gpio"
                except Exception as exc:
                    log.warning("RGB LED unavailable (%s); continuing without it", exc)
            self._colors = {k: tuple(int(bool(v)) for v in rgb) for k, rgb in cfg["colors"].items()}
            self._flash_seconds = float(cfg["flash_seconds"])
            self._current = None

    def flash(self, name):
        with self._lock:
            self._flash = name
            self._flash_until = time.monotonic() + self._flash_seconds

    def preview(self, rgb, seconds=3.0):
        """Show an arbitrary colour (LED test from the web); wins over everything."""
        with self._lock:
            self._preview = tuple(int(bool(v)) for v in rgb)
            self._preview_until = time.monotonic() + float(seconds)

    def test_sequence(self, step=0.7):
        """Red, green, blue, white, off — in the background."""
        def run():
            for rgb in ((1, 0, 0), (0, 1, 0), (0, 0, 1), (1, 1, 1)):
                self.preview(rgb, step + 0.2)
                time.sleep(step)
            with self._lock:
                self._preview_until = 0.0
        threading.Thread(target=run, name="led-test", daemon=True).start()

    def set_condition(self, name, active):
        with self._lock:
            if active:
                self._conditions.add(name)
            else:
                self._conditions.discard(name)

    def desired(self, now=None):
        now = time.monotonic() if now is None else now
        with self._lock:
            if self._preview is not None and now < self._preview_until:
                return self._preview
            if self._flash and now < self._flash_until:
                return self._colors.get(self._flash, OFF)
            for name in PRIORITY:
                if name in self._conditions:
                    return self._colors.get(name, OFF)
        return OFF

    def tick(self):
        rgb = self.desired()
        if rgb != self._current:
            with self._lock:
                self.pins.write(rgb)
            self._current = rgb

    def lamp_test(self):
        for rgb in ((1, 0, 0), (0, 1, 0), (0, 0, 1), OFF):
            with self._lock:
                self.pins.write(rgb)
            time.sleep(0.3)
        self._current = None

    def start(self):
        def run():
            self.lamp_test()
            while not self._stop.wait(0.1):
                try:
                    self.tick()
                except Exception:
                    log.exception("LED update failed")
        self._thread = threading.Thread(target=run, name="leds", daemon=True)
        self._thread.start()
        return self

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(2)
        with self._lock:
            self.pins.write(OFF)
            self.pins.close()
