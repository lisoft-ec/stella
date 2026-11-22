"""IoU tracker (port of the original ``persona.py`` without class-level state)."""


def iou(a, b):
    """Intersection over union of two (x1, y1, x2, y2) boxes."""
    xa, ya = max(a[0], b[0]), max(a[1], b[1])
    xb, yb = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, xb - xa) * max(0, yb - ya)
    if inter == 0:
        return 0.0
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    return inter / float(area_a + area_b - inter)


class Track:
    __slots__ = ("id", "box", "missing", "hits")

    def __init__(self, track_id, box):
        self.id = track_id
        self.box = box
        self.missing = 0
        self.hits = 1

    def __repr__(self):
        return "Track(%d, %r)" % (self.id, self.box)


class IoUTracker:
    def __init__(self, iou_threshold=0.2, max_missing=5):
        self.iou_threshold = iou_threshold
        self.max_missing = max_missing
        self.tracks = []
        self._next_id = 1

    def update(self, boxes):
        """Associate detections with tracks.

        Returns ``(updated, closed)``: tracks seen this frame (new or matched),
        and tracks removed because they went undetected for too long.
        """
        pairs = []
        for di, box in enumerate(boxes):
            for track in self.tracks:
                score = iou(box, track.box)
                if score > self.iou_threshold:
                    pairs.append((score, di, track))
        # Greedy global assignment: best overlaps first.
        pairs.sort(key=lambda p: p[0], reverse=True)
        used_dets, used_tracks = set(), set()
        updated = []
        for _, di, track in pairs:
            if di in used_dets or track.id in used_tracks:
                continue
            used_dets.add(di)
            used_tracks.add(track.id)
            track.box = boxes[di]
            track.missing = 0
            track.hits += 1
            updated.append(track)

        for di, box in enumerate(boxes):
            if di not in used_dets:
                track = Track(self._next_id, box)
                self._next_id += 1
                self.tracks.append(track)
                updated.append(track)

        closed = []
        alive = []
        for track in self.tracks:
            if track.id not in used_tracks and track not in updated:
                track.missing += 1
            if track.missing > self.max_missing:
                closed.append(track)
            else:
                alive.append(track)
        self.tracks = alive
        return updated, closed

    def flush(self):
        """Close every open track (end of a video, reconfiguration)."""
        closed, self.tracks = self.tracks, []
        return closed
