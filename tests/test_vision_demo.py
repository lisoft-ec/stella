"""Detector and full pipeline on the demo video (PC, CPU model)."""
import os

import cv2
import numpy as np
import pytest
import yaml

from stella.config import Config
from stella.pipeline import Pipeline
from stella.video.source import VideoSource
from stella.vision.motion import MotionGate

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEMO = os.path.join(ROOT, "demo", "entrada002.webm")
CPU_MODEL = "models/ssd_mobilenet_v2_coco_quant_postprocess.tflite"
EXPECTED = os.path.join(ROOT, "tests", "data", "demo_expected.yaml")

pytest.importorskip("ai_edge_litert")


@pytest.fixture
def demo_config(tmp_path):
    with open(EXPECTED) as fh:
        expected = yaml.safe_load(fh)
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump({
        "camera": {"source": DEMO, "width": 1280, "height": 720, "realtime": False},
        "detector": {"model": CPU_MODEL, "delegate": "none"},
        "counting": expected["counting"],
    }))
    return Config(str(path)).load(), expected


def demo_frame(index):
    cap = cv2.VideoCapture(DEMO)
    cap.set(cv2.CAP_PROP_POS_FRAMES, index)
    ok, frame = cap.read()
    cap.release()
    assert ok
    return frame


def test_detector_finds_person_in_demo(demo_config):
    from stella.vision.detector import Detector

    config, _ = demo_config
    det = Detector(config.resolve_path(CPU_MODEL), "none")
    found = det.detect(demo_frame(100), threshold=0.5, label=0)
    assert found, "debería detectar a la persona del frame 100"
    x1, y1, x2, y2 = found[0].box
    assert 0 <= x1 < x2 <= 1280 and 0 <= y1 < y2 <= 720
    assert det.last_ms > 0


def test_motion_gate_reacts_to_change():
    gate = MotionGate({"enabled": True, "threshold_percent": 1.0, "idle_frames": 2})
    still = np.zeros((240, 320, 3), np.uint8)
    for _ in range(30):
        gate.update(still)
    assert gate.percent < 1.0
    moving = still.copy()
    moving[60:180, 100:200] = 255
    assert gate.update(moving) is True
    for _ in range(3):
        gate.report_detections(0)
    assert gate.active is False


def test_source_flip_and_resize():
    src = VideoSource({"source": DEMO, "width": 640, "height": 360, "flip_x": True,
                       "flip_y": False, "loop": False, "realtime": False}).open()
    frame = src.read()
    src.close()
    assert frame.shape == (360, 640, 3)


@pytest.mark.slow
def test_demo_video_counts(demo_config):
    config, expected = demo_config
    events = []
    pipeline = Pipeline(config, on_event=lambda d, t: events.append(d))
    pipeline._build_detector()
    source = VideoSource(config.section("camera"), config.resolve_path).open()
    while True:
        frame = source.read()
        if frame is None:
            break
        pipeline.process(frame)
    source.close()
    pipeline._close_tracks()

    counts = {"in": events.count("in"), "out": events.count("out")}
    print("demo counts:", counts)
    assert counts["in"] + counts["out"] > 0, "el vídeo demo tiene cruces"
    if expected.get("in") is None or expected.get("out") is None:
        pytest.xfail("Cifras esperadas pendientes en tests/data/demo_expected.yaml; obtenido %s" % counts)
    assert counts == {"in": expected["in"], "out": expected["out"]}
