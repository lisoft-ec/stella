"""Line-crossing counter inside a polygonal region of interest.

Each track is represented by its foot point (bottom-centre of the box). The
side of the counting line where the track is first seen inside the ROI is
compared with the side where it was last seen when the track closes; if they
differ the person crossed (same rule as the original ``persona.py``).
"""
import cv2
import numpy as np

IN = "in"
OUT = "out"


def foot_point(box):
    return ((box[0] + box[2]) / 2.0, float(box[3]))


def side_of_line(point, p1, p2):
    """-1 / +1 depending on the side of the directed line p1->p2 (0 on it).

    With image coordinates (y down) and a left-to-right line, points below
    the line are +1.
    """
    cross = (p2[0] - p1[0]) * (point[1] - p1[1]) - (p2[1] - p1[1]) * (point[0] - p1[0])
    if cross > 0:
        return 1
    if cross < 0:
        return -1
    return 0


class CrossingCounter:
    def __init__(self, counting_cfg, frame_size):
        self.cfg = counting_cfg
        self.set_frame_size(frame_size)
        self._sides = {}  # track_id -> [first_side, last_side]

    def set_frame_size(self, frame_size):
        w, h = frame_size
        self.frame_size = frame_size
        self.roi = np.array([[x * w, y * h] for x, y in self.cfg["roi"]], dtype=np.float32)
        (x1, y1), (x2, y2) = self.cfg["line"]
        self.p1, self.p2 = (x1 * w, y1 * h), (x2 * w, y2 * h)

    def roi_bbox(self, margin=0.05):
        """Integer bounding box of the ROI (with a margin) clipped to the frame."""
        w, h = self.frame_size
        xs, ys = self.roi[:, 0], self.roi[:, 1]
        mx, my = margin * w, margin * h
        x1 = int(max(0, xs.min() - mx))
        y1 = int(max(0, ys.min() - my))
        x2 = int(min(w, xs.max() + mx))
        y2 = int(min(h, ys.max() + my))
        return x1, y1, x2, y2

    def in_roi(self, box):
        return cv2.pointPolygonTest(self.roi, foot_point(box), False) >= 0

    def side(self, box):
        return side_of_line(foot_point(box), self.p1, self.p2)

    def observe(self, tracks):
        """Record the side of each updated track whose foot is inside the ROI."""
        for track in tracks:
            if not self.in_roi(track.box):
                continue
            s = self.side(track.box)
            if s == 0:
                continue
            sides = self._sides.get(track.id)
            if sides is None:
                self._sides[track.id] = [s, s]
            else:
                sides[1] = s

    def close(self, tracks):
        """Evaluate closed tracks; returns a list of ``(direction, track)``."""
        events = []
        for track in tracks:
            sides = self._sides.pop(track.id, None)
            if not sides or sides[0] == sides[1]:
                continue
            forward = sides[0] < 0 < sides[1]
            if self.cfg.get("invert"):
                forward = not forward
            events.append((IN if forward else OUT, track))
        return events

    def side_of_track(self, track_id):
        sides = self._sides.get(track_id)
        return sides[1] if sides else 0

    def reset(self):
        self._sides.clear()
