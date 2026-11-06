"""Isolated camera/driver diagnostics. No models, database access, or image files.

Run from backend: python -m app.vision.camera_diagnostics --indices 0 1 2 --preview
Each index/backend runs in its own bounded child process so a hung driver is killed.
"""
import argparse
import importlib.metadata
import json
import math
import platform
import struct
import subprocess
import sys
import time


def frame_statistics(frame):
    import numpy as np
    result = {"shape": list(frame.shape), "dtype": str(frame.dtype)}
    if frame.ndim != 3 or frame.shape[2] != 3 or not frame.size:
        result["warning"] = "Not a three-channel BGR image; may be a raw/unsupported pixel format."
        return result
    sample = frame[::max(1, frame.shape[0] // 64), ::max(1, frame.shape[1] // 64)].astype(float)
    b, g, r = sample[..., 0], sample[..., 1], sample[..., 2]
    result.update(mean_bgr=[round(float(channel.mean()), 2) for channel in (b, g, r)],
                  std_bgr=[round(float(channel.std()), 2) for channel in (b, g, r)],
                  green_dominant_fraction=round(float(np.mean((g > b + 40) & (g > r + 40))), 3))
    return result


def probe(index, backend, preview=False, convert_rgb="default"):
    import cv2
    from app.vision.camera_source import open_camera
    result = {"index": index, "requested_backend": backend, "status": "failed", "opencv": cv2.__version__}
    camera = None
    try:
        camera = open_camera(index, backend, phone=False)
        if convert_rgb != "default":
            result["set_convert_rgb_accepted"] = bool(camera.set(cv2.CAP_PROP_CONVERT_RGB, int(convert_rgb == "on")))
        try:
            result["actual_backend"] = camera.getBackendName()
        except cv2.error:
            result["actual_backend"] = "unreported"
        for label, prop in (("width", cv2.CAP_PROP_FRAME_WIDTH), ("height", cv2.CAP_PROP_FRAME_HEIGHT),
                            ("fps_reported", cv2.CAP_PROP_FPS), ("convert_rgb_reported", cv2.CAP_PROP_CONVERT_RGB)):
            value = camera.get(prop)
            result[label] = value if math.isfinite(value) else None
        fourcc = camera.get(cv2.CAP_PROP_FOURCC)
        result["fourcc"] = "".join(chr((int(fourcc) >> (8 * i)) & 255) for i in range(4)) if math.isfinite(fourcc) else "unreported"
        frames = []
        deadline = time.monotonic() + 4
        first = time.monotonic()
        while len(frames) < 10 and time.monotonic() < deadline:
            ok, frame = camera.read()
            if ok and frame is not None and frame.size:
                frames.append(frame)
            else:
                time.sleep(.05)
        result["frames_read"] = len(frames)
        result["read_seconds"] = round(time.monotonic() - first, 3)
        if not frames:
            raise RuntimeError("Device opened but supplied no usable frames")
        result.update(status="frames_received", frame=frame_statistics(frames[-1]))
        result["first_last_mean_difference"] = round(float(abs(frames[-1].astype(float) - frames[0].astype(float)).mean()), 3) if frames[-1].shape == frames[0].shape else None
        if preview:
            try:
                cv2.imshow(f"Diagnostic: #{index} / {backend} - inspect image (3 sec)", frames[-1])
                cv2.waitKey(3000)
            except cv2.error as exc:
                result["preview_error"] = str(exc)
    except Exception as exc:
        result["error"] = str(exc)
    finally:
        if camera is not None:
            camera.release()
        try:
            cv2.destroyAllWindows()
        except cv2.error:
            pass
    return result


def run_probe(index, backend, timeout=20, preview=False, convert_rgb="default"):
    args = [sys.executable, "-u", "-m", "app.vision.camera_diagnostics", "--probe", "--indices", str(index), "--backends", backend, "--convert-rgb", convert_rgb]
    if preview:
        args.append("--preview")
    try:
        process = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, shell=False)
    except subprocess.TimeoutExpired:
        return {"index": index, "requested_backend": backend, "status": "timeout", "error": f"Driver exceeded {timeout}s; probe process was killed"}
    marker = "CAMERA_DIAGNOSTIC_JSON="
    payload = next((line[len(marker):] for line in reversed(process.stdout.splitlines()) if line.startswith(marker)), None)
    try:
        result = json.loads(payload) if payload else {"index": index, "requested_backend": backend, "status": "crashed", "error": "Probe exited without a report"}
    except json.JSONDecodeError:
        result = {"index": index, "requested_backend": backend, "status": "crashed", "error": "Invalid probe report"}
    result["exit_code"] = process.returncode
    if process.stderr.strip():
        result["driver_messages"] = process.stderr.strip()[-2000:]
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--indices", nargs="+", type=int, default=[0, 1, 2])
    parser.add_argument("--backends", nargs="+", choices=["auto", "dshow", "msmf"], default=["auto", "dshow", "msmf"] if sys.platform == "win32" else ["auto"])
    parser.add_argument("--preview", action="store_true", help="Show each readable feed briefly on this PC; images are never saved")
    parser.add_argument("--timeout", type=int, default=20, help="Maximum seconds per isolated index/backend probe (5-60)")
    parser.add_argument("--convert-rgb", choices=["default", "on", "off"], default="default", help="Only change for a targeted follow-up diagnostic; defaults to driver settings")
    parser.add_argument("--probe", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if any(index < 0 or index > 10 for index in args.indices) or not 5 <= args.timeout <= 60:
        parser.error("Indices must be 0-10 and timeout 5-60 seconds")
    if args.probe:
        result = probe(args.indices[0], args.backends[0], args.preview, args.convert_rgb)
        print("CAMERA_DIAGNOSTIC_JSON=" + json.dumps(result), flush=True)
        raise SystemExit(0 if result["status"] == "frames_received" else 1)
    print("CAMERA DIAGNOSTICS — stop dashboard recognition/checks first; keep DroidCam connected.")
    print(f"Python: {sys.version.split()[0]} ({struct.calcsize('P') * 8}-bit), {sys.executable}")
    print(f"OS: {platform.platform()} / platform={sys.platform}")
    for package in ("opencv-python", "opencv-contrib-python", "opencv-python-headless", "opencv-contrib-python-headless"):
        try:
            print(f"Installed: {package}=={importlib.metadata.version(package)}")
        except importlib.metadata.PackageNotFoundError:
            pass
    print("No video/photos are saved, no recognition runs, and no attendance is written.")
    print("Green statistics/motion differences are clues only, not an automatic corruption or device-identity verdict.")
    print(f"Testing {len(args.indices) * len(args.backends)} combinations; up to {args.timeout}s each. Ctrl+C stops the run.\n", flush=True)
    for index in args.indices:
        for backend in args.backends:
            print(f"=== camera {index} / {backend} ===", flush=True)
            print(json.dumps(run_probe(index, backend, args.timeout, args.preview, args.convert_rgb), indent=2), flush=True)
    print("Done. Report which preview showed the phone, which was green, and which failed. Do not run recognition concurrently.")


if __name__ == "__main__":
    main()
