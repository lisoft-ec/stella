from stella.vision.counting import IN, OUT, CrossingCounter, side_of_line
from stella.vision.tracker import IoUTracker, iou

FULL_ROI = [[0, 0], [1, 0], [1, 1], [0, 1]]


def counting_cfg(**kw):
    cfg = {"roi": FULL_ROI, "line": [[0, 0.5], [1, 0.5]], "invert": False}
    cfg.update(kw)
    return cfg


def box_at(cx, foot_y, w=40, h=120):
    return (int(cx - w / 2), int(foot_y - h), int(cx + w / 2), int(foot_y))


def run(boxes_per_frame, cfg=None, max_missing=2, size=(400, 400)):
    tracker = IoUTracker(0.2, max_missing)
    counter = CrossingCounter(cfg or counting_cfg(), size)
    events = []
    for boxes in boxes_per_frame:
        updated, closed = tracker.update(boxes)
        counter.observe(updated)
        events += counter.close(closed)
    events += counter.close(tracker.flush())
    return events


def walk(y_from, y_to, steps=12, cx=200):
    return [[box_at(cx, y_from + (y_to - y_from) * i / float(steps - 1))] for i in range(steps)]


def test_iou():
    assert iou((0, 0, 10, 10), (0, 0, 10, 10)) == 1.0
    assert iou((0, 0, 10, 10), (20, 20, 30, 30)) == 0.0
    assert abs(iou((10, 10, 50, 50), (40, 10, 60, 50)) - 400.0 / 2000.0) < 1e-9


def test_side_of_line_image_coordinates():
    assert side_of_line((5, 10), (0, 5), (10, 5)) == 1   # below
    assert side_of_line((5, 0), (0, 5), (10, 5)) == -1   # above
    assert side_of_line((5, 5), (0, 5), (10, 5)) == 0


def test_walking_down_is_in_and_up_is_out():
    events = run(walk(120, 380))
    assert [d for d, _ in events] == [IN]
    events = run(walk(380, 120))
    assert [d for d, _ in events] == [OUT]


def test_invert_swaps_direction():
    events = run(walk(120, 380), cfg=counting_cfg(invert=True))
    assert [d for d, _ in events] == [OUT]


def test_no_crossing_no_event():
    assert run(walk(120, 180)) == []
    # Goes past the line and comes back: same side at start and end.
    there_and_back = walk(150, 300) + walk(300, 150)
    assert run(there_and_back) == []


def test_track_survives_short_gaps_and_closes_after_max_missing():
    frames = walk(120, 260, steps=6) + [[], []] + walk(280, 380, steps=6)
    events = run(frames, max_missing=3)
    assert [d for d, _ in events] == [IN]
    # A gap longer than max_missing splits the walk into two tracks: no crossing.
    frames = walk(120, 190, steps=6) + [[]] * 5 + walk(310, 380, steps=6)
    assert run(frames, max_missing=2) == []


def test_outside_roi_is_ignored():
    cfg = counting_cfg(roi=[[0, 0], [0.4, 0], [0.4, 1], [0, 1]])
    assert run(walk(120, 380, cx=300), cfg=cfg) == []
    assert len(run(walk(120, 380, cx=100), cfg=cfg)) == 1


def test_two_people_crossing_opposite_directions():
    down = walk(120, 380, cx=100)
    up = walk(380, 120, cx=300)
    frames = [a + b for a, b in zip(down, up)]
    directions = sorted(d for d, _ in run(frames))
    assert directions == [IN, OUT]


def test_slanted_line():
    # Diagonal line from top-left to bottom-right; moving left->right across it.
    cfg = counting_cfg(line=[[0, 0], [1, 1]])
    frames = [[box_at(x, 300)] for x in range(150, 400, 20)]
    events = run(frames, cfg=cfg)
    assert len(events) == 1


def test_tracker_ids_and_close():
    tracker = IoUTracker(0.2, 1)
    updated, closed = tracker.update([(0, 0, 10, 10)])
    assert [t.id for t in updated] == [1] and closed == []
    updated, _ = tracker.update([(1, 0, 11, 10), (100, 100, 110, 110)])
    assert sorted(t.id for t in updated) == [1, 2]
    tracker.update([])
    _, closed = tracker.update([])
    assert sorted(t.id for t in closed) == [1, 2]
    assert tracker.tracks == []
