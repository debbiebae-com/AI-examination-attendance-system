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
        # Request, not a guarantee: the virtual camera driver decides supported modes.
        try:
            camera.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
            camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
            camera.set(cv2.CAP_PROP_FPS, 30)
        except cv2.error:
            print("Camera driver rejected a requested mode; using its default resolution/FPS.", flush=True)
    return camera
