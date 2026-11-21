"""Processing loop: source -> MOG2 gate -> detector -> tracker -> line counter."""
import logging
import threading
import time

import cv2

from .video.source import SourceError, VideoSource
from .vision.counting import CrossingCounter
from .vision.detector import Detector
from .vision.motion import MotionGate
from .vision.tracker import IoUTracker

log = logging.getLogger(__name__)

RELOAD_SOURCE = ("camera",)
RELOAD_DETECTOR = ("detector",)
RELOAD_LIGHT = ("motion", "tracking", "counting", "web")


class Pipeline:
    def __init__(self, config, on_event=None, detector=None):
        """``on_event(direction, track)`` is called for every counted crossing."""
        self.config = config
        self.on_event = on_event
        self._detector = detector
        self._own_detector = detector is None
        self.source = None
        self._thread = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._pending = set()
        self._cond = threading.Condition()
        self._seq = 0
        self._jpeg = None
        self._jpeg_seq = 0
        self._last_preview = 0.0
        self._last_frame_t = None
        self.finished = False
        self._snapshot = {
            "running": False, "error": None, "fps": 0.0, "inference_ms": 0.0,
            "motion": 0.0, "active": False, "frame": [0, 0], "tracks": [],
        }
        self._build_light()

    # -- construction ------------------------------------------------------
    def _build_light(self):
        cfg = self.config
        self.motion = MotionGate(cfg.section("motion"))
        trk = cfg.section("tracking")
        self.tracker = IoUTracker(trk["iou_threshold"], trk["max_missing"])
        cam = cfg.section("camera")
        self.counter = CrossingCounter(cfg.section("counting"), (cam["width"], cam["height"]))
        det = cfg.section("detector")
        self._det_params = (det["threshold"], det["max_objects"], det["person_label"])
        web = cfg.section("web")
        self._preview = (max(0.5, float(web["preview_fps"])), int(web["preview_width"]),
                         int(web["jpeg_quality"]))

    def _build_detector(self):
        det = self.config.section("detector")
        self._detector = Detector(self.config.resolve_path(det["model"]), det["delegate"],
                                  det.get("threads", 2))

    def _open_source(self):
        self.source = VideoSource(self.config.section("camera"), self.config.resolve_path).open()

    def request_reload(self, section):
        """Called by config listeners; applied by the processing thread."""
        with self._lock:
            self._pending.add(section)

    def _apply_reloads(self):
        with self._lock:
            pending, self._pending = self._pending, set()
        if not pending:
            return
        log.info("Reloading pipeline sections: %s", ", ".join(sorted(pending)))
        if pending & set(RELOAD_SOURCE) and self.source is not None:
            self.source.close()
            self.source = None
        if pending & set(RELOAD_DETECTOR) and self._own_detector:
            self._detector = None
        if pending & set(RELOAD_LIGHT + RELOAD_SOURCE + RELOAD_DETECTOR):
            self._close_tracks()
            self._build_light()

    # -- processing --------------------------------------------------------
    def process(self, frame):
        """Process one BGR frame. Returns the list of ``(direction, track)`` events."""
        h, w = frame.shape[:2]
        if self.counter.frame_size != (w, h):
            self.counter.set_frame_size((w, h))
        x1, y1, x2, y2 = self.counter.roi_bbox()
        crop = frame[y1:y2, x1:x2]

        detections = []
        run = self.motion.update(crop)
        if run and crop.size:
            threshold, max_objects, label = self._det_params
            for d in self._detector.detect(crop, threshold, max_objects, label):
                box = (d.box[0] + x1, d.box[1] + y1, d.box[2] + x1, d.box[3] + y1)
                if self.counter.in_roi(box):
                    detections.append(box)
            self.motion.report_detections(len(detections))

        updated, closed = self.tracker.update(detections)
        self.counter.observe(updated)
        events = self.counter.close(closed)
        self._emit(events)
        self._update_snapshot(w, h, run)
        return events

    def _emit(self, events):
        for direction, track in events:
            log.info("Crossing %s (track %d)", direction, track.id)
            if self.on_event is not None:
                try:
                    self.on_event(direction, track)
                except Exception:
                    log.exception("on_event callback failed")

    def _close_tracks(self):
        """Count the tracks still open (end of video, reconfiguration)."""
        events = self.counter.close(self.tracker.flush())
        self._emit(events)
        return events

    def _update_snapshot(self, w, h, active):
        now = time.monotonic()
        fps = self._snapshot["fps"]
        if self._last_frame_t is not None:
            dt = now - self._last_frame_t
            if dt > 0:
                fps = 0.9 * fps + 0.1 * (1.0 / dt) if fps else 1.0 / dt
        self._last_frame_t = now
        tracks = [{
            "id": t.id,
            "box": [t.box[0] / float(w), t.box[1] / float(h), t.box[2] / float(w), t.box[3] / float(h)],
            "side": self.counter.side_of_track(t.id),
            "missing": t.missing,
        } for t in self.tracker.tracks]
        with self._cond:
            self._snapshot.update({
                "running": True, "error": None, "fps": round(fps, 1),
                "inference_ms": round(self._detector.last_ms if self._detector else 0.0, 1),
                "motion": round(self.motion.percent, 2), "active": bool(active),
                "frame": [w, h], "tracks": tracks,
            })
            self._seq += 1
            self._cond.notify_all()

    def _encode_preview(self, frame):
        fps, width, quality = self._preview
        now = time.monotonic()
        if now - self._last_preview < 1.0 / fps:
            return
        self._last_preview = now
        h, w = frame.shape[:2]
        if w > width:
            frame = cv2.resize(frame, (width, int(h * width / float(w))), interpolation=cv2.INTER_AREA)
        ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
        if ok:
            with self._cond:
                self._jpeg = buf.tobytes()
                self._jpeg_seq += 1
                self._cond.notify_all()

    # -- consumers ---------------------------------------------------------
    def snapshot(self):
        with self._cond:
            snap = dict(self._snapshot)
            snap["tracks"] = list(snap["tracks"])
            return snap

    def wait_snapshot(self, last_seq, timeout=1.0):
        with self._cond:
            if self._seq == last_seq:
                self._cond.wait(timeout)
            return self._seq, self.snapshot_unlocked()

    def snapshot_unlocked(self):
        snap = dict(self._snapshot)
        snap["tracks"] = list(snap["tracks"])
        return snap

    def wait_jpeg(self, last_seq, timeout=2.0):
        with self._cond:
            if self._jpeg_seq == last_seq:
                self._cond.wait(timeout)
            return self._jpeg_seq, self._jpeg

    # -- thread ------------------------------------------------------------
    def start(self):
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="pipeline", daemon=True)
        self._thread.start()
        return self

    def stop(self, timeout=5.0):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout)
        if self.source is not None:
            self.source.close()
            self.source = None

    def join(self, timeout=None):
        if self._thread is not None:
            self._thread.join(timeout)

    def _set_error(self, message, level=logging.ERROR):
        log.log(level, "Pipeline stopped: %s", message)
        with self._cond:
            self._snapshot.update({"running": False, "error": message})
            self._seq += 1
            self._cond.notify_all()

    def _run(self):
        while not self._stop.is_set():
            try:
                self._apply_reloads()
                if self._detector is None:
                    self._build_detector()
                if self.source is None:
                    self._open_source()
                    self.finished = False
                frame = self.source.read()
                if frame is None:
                    if self.source.is_file:
                        self._close_tracks()
                        self.finished = True
                        self._set_error("Fin del archivo de vídeo", logging.INFO)
                        # Wait for a reconfiguration (or stop) before reopening.
                        while not self._stop.is_set() and not self._pending:
                            time.sleep(0.5)
                        self.source.close()
                        self.source = None
                        continue
                    raise SourceError("La cámara no entrega imágenes")
                self.process(frame)
                self._encode_preview(frame)
            except Exception as exc:
                self._set_error(str(exc))
                if self.source is not None:
                    self.source.close()
                    self.source = None
                self._stop.wait(5.0)
        self._close_tracks()
