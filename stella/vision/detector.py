"""SSD person detector on TFLite: Edge TPU delegate (Coral) or CPU (PC)."""
import logging
import time

import cv2
import numpy as np

log = logging.getLogger(__name__)

EDGETPU_LIB = "libedgetpu.so.1"


def _interpreter_class():
    """Prefer tflite_runtime (Coral board), fall back to ai_edge_litert (PC)."""
    try:
        from tflite_runtime.interpreter import Interpreter, load_delegate
    except ImportError:
        from ai_edge_litert.interpreter import Interpreter, load_delegate
    return Interpreter, load_delegate


class Detection:
    __slots__ = ("box", "score", "label")

    def __init__(self, box, score, label):
        self.box = box  # (x1, y1, x2, y2) in pixels of the analysed frame
        self.score = score
        self.label = label

    def __repr__(self):
        return "Detection(%r, %.2f, %d)" % (self.box, self.score, self.label)


class Detector:
    def __init__(self, model_path, delegate="none", threads=2):
        Interpreter, load_delegate = _interpreter_class()
        if delegate == "edgetpu":
            self.interpreter = Interpreter(
                model_path=model_path, experimental_delegates=[load_delegate(EDGETPU_LIB)])
        else:
            try:
                self.interpreter = Interpreter(model_path=model_path, num_threads=threads)
            except TypeError:
                self.interpreter = Interpreter(model_path=model_path)
        self.interpreter.allocate_tensors()
        inp = self.interpreter.get_input_details()[0]
        self._input_index = inp["index"]
        _, self.in_h, self.in_w, _ = inp["shape"]
        self._input_dtype = inp["dtype"]
        self._outputs = self._map_outputs(self.interpreter.get_output_details())
        self.last_ms = 0.0
        log.info("Detector loaded: %s (delegate=%s, input=%dx%d)", model_path, delegate, self.in_w, self.in_h)

    @staticmethod
    def _map_outputs(details):
        """Find boxes/classes/scores/count among the SSD post-process outputs."""
        by_size = {}
        boxes = count = None
        rest = []
        for d in details:
            shape = list(d["shape"])
            if shape and shape[-1] == 4 and len(shape) == 3:
                boxes = d["index"]
            elif int(np.prod(shape)) == 1:
                count = d["index"]
            else:
                rest.append(d)
        if boxes is None or count is None or len(rest) != 2:
            raise ValueError("El modelo no tiene las salidas SSD esperadas")
        # TF1 models name them ...:1 (classes) and ...:2 (scores).
        rest.sort(key=lambda d: d["name"])
        by_size["boxes"], by_size["count"] = boxes, count
        by_size["classes"], by_size["scores"] = rest[0]["index"], rest[1]["index"]
        return by_size

    def detect(self, frame_bgr, threshold=0.5, max_objects=10, label=None):
        """Run inference on a BGR frame; returns detections in its pixel coordinates.

        The frame is letterboxed (aspect ratio kept, padded bottom/right) like
        pycoral's ``keep_aspect_ratio=True`` used by the original code.
        """
        h, w = frame_bgr.shape[:2]
        scale = min(float(self.in_w) / w, float(self.in_h) / h)
        nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
        resized = cv2.resize(frame_bgr, (nw, nh), interpolation=cv2.INTER_LINEAR)
        tensor = np.zeros((self.in_h, self.in_w, 3), dtype=np.uint8)
        tensor[:nh, :nw] = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        self.interpreter.set_tensor(self._input_index, tensor[np.newaxis].astype(self._input_dtype))

        start = time.monotonic()
        self.interpreter.invoke()
        self.last_ms = (time.monotonic() - start) * 1000.0

        get = self.interpreter.get_tensor
        boxes = get(self._outputs["boxes"])[0]
        classes = get(self._outputs["classes"])[0]
        scores = get(self._outputs["scores"])[0]
        count = int(get(self._outputs["count"]).flatten()[0])

        results = []
        for i in range(min(count, len(scores))):
            score = float(scores[i])
            if score < threshold:
                continue
            cls = int(classes[i])
            if label is not None and cls != label:
                continue
            ymin, xmin, ymax, xmax = boxes[i]
            # Normalized to the padded input -> pixels of the original frame.
            x1 = int(max(0.0, xmin) * self.in_w / scale)
            y1 = int(max(0.0, ymin) * self.in_h / scale)
            x2 = int(min(1.0, xmax) * self.in_w / scale)
            y2 = int(min(1.0, ymax) * self.in_h / scale)
            x1, x2 = min(x1, w), min(x2, w)
            y1, y2 = min(y1, h), min(y2, h)
            if x2 > x1 and y2 > y1:
                results.append(Detection((x1, y1, x2, y2), score, cls))
        results.sort(key=lambda d: d.score, reverse=True)
        return results[:max_objects]
