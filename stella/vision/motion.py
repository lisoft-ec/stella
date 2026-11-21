"""MOG2 motion gate: only run inference while something moves in the ROI."""
import cv2
import numpy as np

# MOG2 runs on a downscaled copy for speed; the percentage is scale independent.
MAX_WIDTH = 320


class MotionGate:
    def __init__(self, motion_cfg):
        self.cfg = motion_cfg
        self.enabled = bool(motion_cfg.get("enabled", True))
        self.subtractor = cv2.createBackgroundSubtractorMOG2(
            history=int(motion_cfg.get("history", 500)),
            varThreshold=float(motion_cfg.get("var_threshold", 16)),
            detectShadows=True,
        )
        self.active = not self.enabled
        self.percent = 0.0
        self._idle = 0

    def update(self, roi_frame):
        """Feed the ROI crop; returns True if inference should run on this frame."""
        if not self.enabled:
            self.active = True
            return True
        h, w = roi_frame.shape[:2]
        if w > MAX_WIDTH:
            roi_frame = cv2.resize(roi_frame, (MAX_WIDTH, max(1, int(h * MAX_WIDTH / w))),
                                   interpolation=cv2.INTER_AREA)
        mask = self.subtractor.apply(roi_frame)
        # 255 = foreground; 127 = shadow (ignored, like the original code).
        self.percent = 100.0 * float(np.count_nonzero(mask == 255)) / mask.size
        if self.percent > self.cfg["threshold_percent"]:
            self.active = True
        return self.active

    def report_detections(self, count):
        """After inference: switch off after ``idle_frames`` frames without people."""
        if not self.enabled:
            return
        if count == 0:
            self._idle += 1
            if self._idle > self.cfg["idle_frames"]:
                self.active = False
                self._idle = 0
        else:
            self._idle = 0
