"""Read a selected camera and show a brief local preview; no recognition/database writes."""
import argparse
import time
from app.vision.camera_source import open_camera


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--camera", type=int, required=True)
    parser.add_argument("--capture-backend", choices=["auto", "dshow", "msmf"], default="auto")
    parser.add_argument("--camera-source", choices=["pc", "droidcam"], default="pc")
    args = parser.parse_args()
    import cv2
    camera = None
    try:
        print(f"Checking {args.camera_source}: camera {args.camera}, backend {args.capture_backend} (no attendance is recorded)", flush=True)
        camera = open_camera(args.camera, args.capture_backend, args.camera_source == "droidcam")
        deadline = time.monotonic() + 6
        frame = None
        while time.monotonic() < deadline:
            ok, candidate = camera.read()
            if ok and candidate is not None and candidate.size:
                frame = candidate
                break
        if frame is None:
            raise RuntimeError("Camera opened but supplied no usable frames. Check the DroidCam connection and camera permissions.")
        height, width = frame.shape[:2]
        print(f"CAMERA CHECK PASSED: received {width} x {height} frame. Confirm this is the intended camera in the local preview; a readable device does not prove it is your phone.", flush=True)
        try:
            cv2.imshow("Camera check - closes after 4 seconds (no attendance)", frame)
            cv2.waitKey(4000)
        except cv2.error:
            print("Local preview unavailable; frame reception succeeded.", flush=True)
    except Exception as exc:
        raise SystemExit(f"CAMERA CHECK FAILED: {exc}")
    finally:
        if camera is not None:
            camera.release()
        try:
            cv2.destroyAllWindows()
        except cv2.error:
            pass


if __name__ == "__main__":
    main()
