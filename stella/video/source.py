"""Frame source: V4L2 camera, camera index or video file, through OpenCV."""
import logging
import os
import time

import cv2

log = logging.getLogger(__name__)

# Coral Dev Board camera (OV5645): writing "1" disables the autofocus.
AF_SYSFS_NODE = "/sys/module/ov5645_camera_mipi_v2/parameters/ov5645_af"


class SourceError(RuntimeError):
    pass


class VideoSource:
    def __init__(self, camera_cfg, resolve_path=None):
        self.cfg = camera_cfg
        self._resolve = resolve_path or (lambda p: p)
        self.cap = None
        self.is_file = False
        self.file_fps = 0.0
        self._next_frame_at = 0.0
        self._af_done = False

    def open(self):
        src = self.cfg["source"]
        if isinstance(src, str) and not src.startswith("/dev/"):
            path = self._resolve(src)
            if not os.path.isfile(path):
                raise SourceError("No existe el archivo de vídeo: %s" % path)
            self.cap = cv2.VideoCapture(path)
            self.is_file = True
            self.file_fps = self.cap.get(cv2.CAP_PROP_FPS) or 0.0
        else:
            backend = cv2.CAP_V4L2 if hasattr(cv2, "CAP_V4L2") else cv2.CAP_ANY
            self.cap = cv2.VideoCapture(src, backend)
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.cfg["width"])
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.cfg["height"])
            self.cap.set(cv2.CAP_PROP_FPS, self.cfg["fps"])
        if not self.cap.isOpened():
            raise SourceError("No se pudo abrir la fuente de vídeo: %s" % src)
        log.info("Video source opened: %s (file=%s)", src, self.is_file)
        return self

    def close(self):
        if self.cap is not None:
            self.cap.release()
            self.cap = None

    def _disable_autofocus(self):
        self._af_done = True
        if not self.cfg.get("disable_autofocus") or self.is_file:
            return
        if os.path.exists(AF_SYSFS_NODE):
            try:
                with open(AF_SYSFS_NODE, "w") as fh:
                    fh.write("1")
                log.info("Camera autofocus disabled")
            except OSError as exc:
                log.warning("Could not disable autofocus: %s", exc)

    def _pace(self):
        """Play video files at their native speed when ``realtime`` is set."""
        if not (self.is_file and self.cfg.get("realtime") and self.file_fps > 0):
            return
        now = time.monotonic()
        if self._next_frame_at > now:
            time.sleep(self._next_frame_at - now)
        self._next_frame_at = max(now, self._next_frame_at) + 1.0 / self.file_fps

    def read(self):
        """Return the next BGR frame, or None when the source is exhausted/failed."""
        if self.cap is None:
            return None
        self._pace()
        ok, frame = self.cap.read()
        if not ok and self.is_file and self.cfg.get("loop"):
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = self.cap.read()
        if not ok or frame is None:
            return None
        if not self._af_done:
            self._disable_autofocus()
        return self.prepare(frame)

    def prepare(self, frame):
        flip_x, flip_y = self.cfg.get("flip_x"), self.cfg.get("flip_y")
        if flip_x and flip_y:
            frame = cv2.flip(frame, -1)
        elif flip_x:
            frame = cv2.flip(frame, 1)
        elif flip_y:
            frame = cv2.flip(frame, 0)
        w, h = self.cfg["width"], self.cfg["height"]
        if frame.shape[1] != w or frame.shape[0] != h:
            frame = cv2.resize(frame, (w, h), interpolation=cv2.INTER_AREA)
        return frame
