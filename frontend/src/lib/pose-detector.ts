import type { Observation } from "./pose"
const failure = (message:string) => Object.assign(new Error(message),{name:"PoseDetectorError"})
export class PoseDetector {
  private worker: Worker
  private sequence=0
  private closed=false
  private pending=new Map<number,{resolve:(value:Observation)=>void;reject:(cause:Error)=>void;timer:ReturnType<typeof setTimeout>}>()
  private lastVideoTime=-1
  constructor() {
    if (typeof Worker==="undefined" || typeof createImageBitmap==="undefined" || typeof OffscreenCanvas==="undefined") throw failure("This browser cannot run head pose checking. Open the page in a current Chrome or Safari browser.")
    this.worker=new Worker(new URL("../workers/pose.worker.ts",import.meta.url),{type:"module"})
    this.worker.onmessage=event=>{
      const task=this.pending.get(event.data.id)
      if(!task)return
      clearTimeout(task.timer);this.pending.delete(event.data.id)
      if(event.data.ok)task.resolve(event.data.observation)
      else task.reject(failure(event.data.error))
    }
    this.worker.onerror=()=>this.close(failure("Head pose checker could not start. Reload this page or try another current browser."))
  }
  private request(message:object, transfer:Transferable[]=[]) {
    return new Promise<Observation>((resolve,reject)=>{
      if(this.closed){reject(failure("Head pose checker was closed"));return}
      const id=++this.sequence
      const timer=setTimeout(()=>{
        this.pending.delete(id);reject(failure("Head pose checker timed out. Check your connection and reload to retry."));this.close()
      },45000)
      this.pending.set(id,{resolve,reject,timer})
      try {this.worker.postMessage({...message,id},transfer)} catch(cause) {clearTimeout(timer);this.pending.delete(id);reject(cause)}
    })
  }
  async init() { await this.request({kind:"init",base:new URL("pose/",document.baseURI).href}) }
  async sample(video:HTMLVideoElement) {
    if (!video.videoWidth || !video.videoHeight || video.readyState < 2 || video.paused || video.ended || video.currentTime <= this.lastVideoTime) return null
    this.lastVideoTime=video.currentTime
    const scale=Math.min(1,640/Math.max(video.videoWidth,video.videoHeight))
    const canvas=document.createElement("canvas")
    canvas.width=Math.round(video.videoWidth*scale);canvas.height=Math.round(video.videoHeight*scale)
    const context=canvas.getContext("2d")
    if(!context)throw failure("This browser cannot read camera frames")
    context.drawImage(video,0,0,canvas.width,canvas.height)
    const image=await createImageBitmap(canvas)
    let observation:Observation
    try {observation=await this.request({kind:"sample",image},[image])} catch(cause){image.close();throw cause}
    // Capture the EXACT checked snapshot, not a later video frame after the worker responds.
    const photo=()=>{
      const mirrored=document.createElement("canvas")
      mirrored.width=canvas.width;mirrored.height=canvas.height
      const ctx=mirrored.getContext("2d")
      if(!ctx)throw failure("This browser cannot capture photos")
      ctx.translate(canvas.width,0);ctx.scale(-1,1);ctx.drawImage(canvas,0,0)
      return mirrored.toDataURL("image/jpeg",0.9)
    }
    return {observation,photo}
  }
  close(cause=failure("Head pose checker was closed")) {
    this.closed=true;this.worker.terminate()
    for(const task of this.pending.values()){clearTimeout(task.timer);task.reject(cause)}
    this.pending.clear()
  }
}
