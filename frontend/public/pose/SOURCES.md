# Browser head-pose model

Model: MediaPipe Face Landmarker float16 task bundle, 3,758,596 bytes.
SHA-256: `64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff`.

Upstream model URL:
https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task

This copy was extracted from the published npm tarball
`@nuralogix.ai/tf-face-tracker-worker-ts@1.0.2`, file
`package/lib/taskVision/model/face_landmarker.task`. Its checksum matches the model
identified by the Git LFS pointer in the MediaPipe TouchDesigner sample repository:
https://github.com/torinmb/mediapipe-touchdesigner/blob/main/src/mediapipe/models/face_landmark_detection/face_landmarker.task

MediaPipe is Apache-2.0 licensed (`APACHE-2.0.txt`). The npm distributor's supplied MIT
notice is retained separately in `LICENSE.txt`. No Nuralogix application code is used.
The app uses the official `@mediapipe/tasks-vision` runtime, pinned by package-lock.json.
Its WASM/loaders are copied into `wasm/` by scripts/prepare-pose-assets.mjs during build.
Do not commit those generated runtime files. No Google/npm/CDN request is required at
runtime: all assets are served from the enrollment site's own origin.
