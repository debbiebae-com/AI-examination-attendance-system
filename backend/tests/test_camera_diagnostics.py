import subprocess
from types import SimpleNamespace
import numpy as np
from app.vision.camera_diagnostics import frame_statistics, run_probe


def test_green_frame_stats_are_not_an_identity_or_failure_verdict():
    frame=np.zeros((20,30,3),dtype=np.uint8);frame[:,:,1]=255
    stats=frame_statistics(frame)
    assert stats["mean_bgr"]==[0,255,0]
    assert stats["std_bgr"]==[0,0,0]
    assert stats["green_dominant_fraction"]==1
    assert "status" not in stats
    assert "warning" in frame_statistics(np.zeros((10,10),dtype=np.uint8))


def test_isolated_probe_reports_metadata_without_models_or_images(monkeypatch):
    calls=[]
    def run(args,**kwargs):
        calls.append((args,kwargs))
        return SimpleNamespace(stdout='driver note\nCAMERA_DIAGNOSTIC_JSON={"status":"frames_received","index":2}\n',stderr="driver warning",returncode=0)
    monkeypatch.setattr(subprocess,"run",run)
    result=run_probe(2,"dshow",preview=True)
    argv,kwargs=calls[0]
    assert argv[argv.index("-m")+1]=="app.vision.camera_diagnostics"
    assert "--preview" in argv and kwargs["shell"] is False
    assert kwargs["timeout"]==20
    assert result["status"]=="frames_received"
    assert result["driver_messages"]=="driver warning"


def test_hung_or_crashed_driver_probes_are_reported(monkeypatch):
    def timeout(args,**kwargs):
        raise subprocess.TimeoutExpired(args,kwargs["timeout"])
    monkeypatch.setattr(subprocess,"run",timeout)
    assert run_probe(1,"msmf")["status"]=="timeout"
    monkeypatch.setattr(subprocess,"run",lambda *a,**k:SimpleNamespace(stdout="",stderr="fatal driver",returncode=5))
    result=run_probe(1,"msmf")
    assert result["status"]=="crashed" and result["exit_code"]==5
