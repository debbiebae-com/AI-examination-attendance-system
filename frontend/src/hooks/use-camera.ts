import { useCallback, useEffect, useRef, useState } from "react"

export type CameraStatus = "requesting" | "ready" | "error"

function cameraMessage(error: unknown) {
  const name = error instanceof DOMException ? error.name : ""
  const messages: Record<string, string> = {
    NotAllowedError: "Camera access was blocked. Allow camera access in your browser's site settings, then try again.",
    NotFoundError: "No camera was found. Connect a camera or open this page on your phone.",
    NotReadableError: "The camera is being used by another app. Close that app and try again.",
    OverconstrainedError: "This camera does not support the requested preview. Try another camera or browser.",
    SecurityError: "Camera access requires a secure HTTPS connection.",
  }
  return messages[name] || "The camera could not start. Check your browser permissions and try again."
}

export function useCamera() {
  const videoRef = useRef<HTMLVideoElement>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const generation = useRef(0)
  const [status, setStatus] = useState<CameraStatus>("requesting")
  const [error, setError] = useState<string | null>(null)

  const release = useCallback(() => {
    streamRef.current?.getTracks().forEach((track) => track.stop())
    streamRef.current = null
    if (videoRef.current) videoRef.current.srcObject = null
  }, [])

  const start = useCallback(async () => {
    const request = ++generation.current
    release()
    setStatus("requesting")
    setError(null)
    if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
      setStatus("error")
      setError("Open this page over HTTPS (or localhost) in a browser that supports camera access.")
      return
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: { facingMode: { ideal: "user" }, width: { ideal: 960 }, height: { ideal: 1280 } },
      })
      if (request !== generation.current) {
        stream.getTracks().forEach((track) => track.stop())
        return
      }
      streamRef.current = stream
      const video = videoRef.current
      if (!video) {
        release()
        return
      }
      video.srcObject = stream
      await video.play()
      if (request !== generation.current) return
      setStatus("ready")
    } catch (cause) {
      if (request !== generation.current) return
      release()
      setStatus("error")
      setError(cameraMessage(cause))
    }
  }, [release])

  useEffect(() => {
    void start()
    return () => {
      generation.current += 1
      release()
    }
  }, [start, release])

  return { videoRef, status, error, retry: start }
}
