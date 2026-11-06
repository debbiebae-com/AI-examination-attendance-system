"""Check model selection without downloading weights or opening a camera."""
import sys
from types import ModuleType, SimpleNamespace

import pytest

from app.vision.embedder import InsightFaceEmbedder


@pytest.mark.parametrize("recognition_only,expected", [
    (False, None), (True, ["detection", "recognition"]),
])
def test_attendance_skips_extra_networks_but_capture_keeps_them(monkeypatch, recognition_only, expected):
    calls = {}

    class FakeAnalysis:
        def __init__(self, **kwargs):
            calls.update(kwargs)

        def prepare(self, **kwargs):
            calls["prepare"] = kwargs

    app = ModuleType("insightface.app")
    app.FaceAnalysis = FakeAnalysis
    monkeypatch.setitem(sys.modules, "insightface.app", app)
    monkeypatch.setitem(sys.modules, "cv2", ModuleType("cv2"))
    monkeypatch.setitem(sys.modules, "onnxruntime", SimpleNamespace(
        SessionOptions=lambda: SimpleNamespace(),
        GraphOptimizationLevel=SimpleNamespace(ORT_ENABLE_ALL=99),
    ))
    InsightFaceEmbedder(recognition_only=recognition_only, liveness=True, threads=4)
    assert calls["allowed_modules"] == expected
    assert calls["name"] == "buffalo_l"
    assert calls["addons"] == ["liveness"]
    assert calls["sess_options"].intra_op_num_threads == 4
