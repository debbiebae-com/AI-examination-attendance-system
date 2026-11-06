/// <reference lib="webworker" />
import { FaceLandmarker, FilesetResolver } from "@mediapipe/tasks-vision"
import { angles, type Observation } from "../lib/pose"
const scope = self as unknown as DedicatedWorkerGlobalScope
let model: FaceLandmarker | null = null
scope.onmessage = async (event: MessageEvent) => {
  const { id, kind, base, image } = event.data
  try {
    if (kind === "init") {
      const files = await FilesetResolver.forVisionTasks(`${base}wasm`, true)
      model = await FaceLandmarker.createFromOptions(files, {
        baseOptions: { modelAssetPath: `${base}face_landmarker.task`, delegate:"CPU" },
        runningMode:"IMAGE", numFaces:2, outputFacialTransformationMatrixes:true,
        minFaceDetectionConfidence:0.6, minFacePresenceConfidence:0.6,
      })
      scope.postMessage({id,ok:true})
      return
    }
    if (!model) throw new Error("Head pose checker is not ready")
    const result = model.detect(image)
    const observation: Observation = {faces:result.faceLandmarks.length}
    if (observation.faces === 1) {
      const landmarks = result.faceLandmarks[0]
      const rotation = angles(result.facialTransformationMatrixes[0]?.data || [])
      if (rotation) Object.assign(observation,rotation)
      const xs=landmarks.map(p=>p.x), ys=landmarks.map(p=>p.y)
      const x1=Math.min(...xs),x2=Math.max(...xs),y1=Math.min(...ys),y2=Math.max(...ys)
      Object.assign(observation,{width:x2-x1,height:y2-y1,cx:(x1+x2)/2,cy:(y1+y2)/2})
    }
    scope.postMessage({id,ok:true,observation})
  } catch {
    scope.postMessage({id,ok:false,error:"Head pose checking failed. Try a current Chrome or Safari browser, reload, and allow the model to finish loading."})
  } finally { image?.close() }
}
