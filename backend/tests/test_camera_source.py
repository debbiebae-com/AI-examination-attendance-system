from types import SimpleNamespace
import pytest
from app.vision import camera_source


def test_camera_default_and_windows_phone_api_selection(monkeypatch):
    cv2=pytest.importorskip("cv2")
    calls=[];settings=[]
    cap=SimpleNamespace(isOpened=lambda:True,set=lambda key,value:settings.append((key,value)),release=lambda:None)
    monkeypatch.setattr(cv2,"VideoCapture",lambda *args:(calls.append(args) or cap))
    monkeypatch.setattr(camera_source,"sys",SimpleNamespace(platform="win32"))
    assert camera_source.open_camera(0) is cap
    assert calls==[(0,)] and not settings
    assert camera_source.open_camera(2,"dshow",True) is cap
    assert calls[-1]==(2,cv2.CAP_DSHOW)
    assert settings==[(cv2.CAP_PROP_FRAME_WIDTH,1280),(cv2.CAP_PROP_FRAME_HEIGHT,720),(cv2.CAP_PROP_FPS,30)]


def test_unavailable_camera_is_released_and_windows_apis_rejected_elsewhere(monkeypatch):
    cv2=pytest.importorskip("cv2")
    released=[]
    monkeypatch.setattr(cv2,"VideoCapture",lambda *args:SimpleNamespace(isOpened=lambda:False,release=lambda:released.append(True)))
    monkeypatch.setattr(camera_source,"sys",SimpleNamespace(platform="linux"))
    with pytest.raises(RuntimeError,match="DroidCam"):
        camera_source.open_camera(1)
    assert released==[True]
    with pytest.raises(ValueError,match="Windows-only"):
        camera_source.open_camera(1,"dshow")
