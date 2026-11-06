"""Shared OpenCV camera selection for recognition and the no-attendance camera check."""
import sys


def open_camera(index: int, backend: str = "auto", phone: bool = False):
    import cv2
    if backend not in ("auto", "dshow", "msmf"):
        raise ValueError("Unsupported camera backend")
    if backend != "auto" and sys.platform != "win32":
        raise ValueError("DirectShow/Media Foundation are Windows-only; choose Automatic")
    api = {"dshow": cv2.CAP_DSHOW, "msmf": cv2.CAP_MSMF}
    camera = cv2.VideoCapture(index) if backend == "auto" else cv2.VideoCapture(index, api[backend])
    if not camera.isOpened():
        camera.release()
        raise RuntimeError(f"Cannot open camera {index} ({backend}). Connect DroidCam in its PC client, close other camera apps, or try another camera number/backend.")
    if phone:
        # Virtual webcam drivers may accept mode changes yet return green/corrupt
        # frames. Keep the working format negotiated by the DroidCam client.
        print("DroidCam: retaining the driver's current resolution and frame rate; no mode overrides.", flush=True)
    return camera
