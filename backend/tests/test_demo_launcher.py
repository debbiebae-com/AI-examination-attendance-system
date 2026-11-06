"""Static launcher contracts on Linux; not a substitute for Windows process smoke tests."""
from pathlib import Path
import sys
from types import SimpleNamespace

from app import demo_setup

ROOT = Path(__file__).resolve().parents[2]


def test_prepare_models_loads_full_configured_pack_without_camera_or_database(monkeypatch, capsys):
    calls = []
    monkeypatch.setitem(sys.modules, "supervision", SimpleNamespace())
    monkeypatch.setattr("app.vision.embedder.InsightFaceEmbedder", lambda **kwargs: calls.append(kwargs))
    monkeypatch.setattr(demo_setup, "ENROLL_MODEL", "configured-model")
    demo_setup.prepare_models()
    assert calls == [{"model_name": "configured-model", "det_size": (480, 480), "threads": 4}]
    assert "No camera or student data was accessed" in capsys.readouterr().out


def test_windows_click_targets_anchor_to_their_own_directory():
    for mode in ("Start", "Prepare", "Stop"):
        contents = (ROOT / f"{mode} Demo.cmd").read_text()
        assert '"%~dp0start-demo.ps1"' in contents
        assert f"-Mode {mode}" in contents
        assert "if errorlevel 1" in contents
        assert "exit /b 1" in contents


def test_start_contract_is_offline_prebuilt_and_health_checked():
    contents = (ROOT / "start-demo.ps1").read_text()
    startup = contents.split("    $prepared = Read-Json $preparedPath", 1)[1]
    assert "'--offline', '--no-sync'" in startup
    assert "node_modules/next/dist/bin/next', 'start'" in startup
    assert "npm ci" not in startup and "npm run dev" not in contents
    assert "Wait-Ready $api 'Backend'" in startup
    assert "Wait-Ready $web 'Dashboard'" in startup
    assert "Get-SourceFingerprint" in startup
    assert "http://127.0.0.1:3000/api/live/session" in contents
    assert "$env:BACKEND_ORIGIN = 'http://127.0.0.1:8000'" in startup


def test_stop_contract_uses_identity_and_owned_trees_not_global_image_kills():
    contents = (ROOT / "start-demo.ps1").read_text()
    assert "actual.created -eq $entry.created" in contents
    assert "Get-OwnedTree $entry" in contents
    assert "Test-OwnedListener $state.api 8000" in contents
    assert "control/camera/stop" in contents
    assert "if ($job.running) { throw" in contents
    assert "Stop-Process -Name" not in contents
    assert "taskkill" not in contents.lower()
    assert "Threading.Mutex" in contents
    assert ".demo-runtime/" in (ROOT / ".gitignore").read_text()
