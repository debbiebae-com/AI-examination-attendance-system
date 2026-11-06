import type { PoseStep } from "./enrollment"
export const HOLD_MS = 600
export const SAMPLE_INTERVAL_MS = 150
export const MAX_SAMPLE_GAP_MS = 1000
export const POSE_TIMEOUT_MS = 45000
export type Observation = { faces: number; yaw?: number; pitch?: number; roll?: number; width?: number; height?: number; cx?: number; cy?: number }
export type PoseCheck = { valid: boolean; message: string }

// MediaPipe FaceGeometry uses column-major matrices, with canonical +Z pointing
// out of the face. On an UNMIRRORED camera image +yaw turns the nose image-right,
// i.e. the person's own LEFT. CSS preview/photo mirroring must not invert this.
export function angles(data: number[]) {
  if (data.length !== 16 || data.some(v=>!Number.isFinite(v))) return null
  if (Math.hypot(data[8],data[9],data[10]) < 0.001) return null
  const degrees = 180 / Math.PI
  return {
    yaw: Math.atan2(data[8], data[10]) * degrees,
    pitch: Math.atan2(-data[9], Math.hypot(data[8],data[10])) * degrees,
    roll: Math.atan2(data[1],data[0]) * degrees,
  }
}
export function checkPose(value: Observation, step: PoseStep): PoseCheck {
  const fail = (message:string) => ({valid:false,message})
  if (!value.faces) return fail("No face found. Face the camera in good light.")
  if (value.faces !== 1) return fail("Only one person should be in the camera view.")
  if ([value.yaw,value.pitch,value.roll,value.width,value.height,value.cx,value.cy].some(v=>v===undefined || !Number.isFinite(v))) return fail("Could not measure your head position. Face the camera clearly.")
  if (value.width! < 0.18) return fail("Move a little closer to the camera.")
  if (value.width! > 0.85 || value.height! > 0.9) return fail("Move a little farther from the camera.")
  if (value.cx! < 0.25 || value.cx! > 0.75 || value.cy! < 0.25 || value.cy! > 0.75) return fail("Move your face toward the center of the view.")
  if (Math.abs(value.pitch!) > 20) return fail("Keep your chin level — do not look up or down.")
  if (Math.abs(value.roll!) > 18) return fail("Keep your head upright — avoid tilting sideways.")
  const yaw = value.yaw!
  if (step === "straight") return Math.abs(yaw) <= 10 ? {valid:true,message:"Looking straight. Hold still."} : fail("Look straight at the camera first.")
  const direction = step === "left" ? 1 : -1
  const turn = yaw * direction
  if (turn < -10) return fail(`That's your ${step === "left" ? "RIGHT" : "LEFT"}. Turn to your ${step.toUpperCase()}.`)
  if (turn < 18) return fail(`Slowly turn a little more to your ${step.toUpperCase()}.`)
  if (turn > 45) return fail("You turned too far. Turn back slightly so both eyes stay visible.")
  return {valid:true,message:`Good ${step} turn. Hold still.`}
}

export class PoseGate {
  private since: number | null = null
  private previous: number | null = null
  private samples = 0
  observe(valid:boolean, now:number) {
    if (!valid || this.previous !== null && now - this.previous > MAX_SAMPLE_GAP_MS) {
      this.since=null; this.samples=0
    }
    this.previous=now
    if (!valid) return {ready:false,held:0}
    this.since ??= now
    this.samples++
    const held = now - this.since
    return {ready: this.samples >= 3 && held >= HOLD_MS, held}
  }
}
