import { beforeEach, expect, it, vi } from "vitest"
import { PoseDetector } from "@/lib/pose-detector"
const observation={faces:1,yaw:25,pitch:0,roll:0,width:0.4,height:0.5,cx:0.5,cy:0.5}
let worker: FakeWorker
class FakeWorker {
 onmessage:((event:{data:unknown})=>void)|null=null
 onerror:(()=>void)|null=null
 terminate=vi.fn()
 postMessage=vi.fn((message:{id:number;kind:string})=>{
  queueMicrotask(()=>this.onmessage?.({data:{id:message.id,ok:true,observation}}))
 })
 constructor(){worker=this}
}
function video() {
 const element=document.createElement("video")
 for(const [key,value] of Object.entries({videoWidth:960,videoHeight:1280,readyState:4,paused:false,ended:false,currentTime:1}))Object.defineProperty(element,key,{value,configurable:true})
 return element
}
beforeEach(()=>{
 vi.stubGlobal("Worker",FakeWorker)
 vi.stubGlobal("OffscreenCanvas",class {})
 vi.stubGlobal("createImageBitmap",vi.fn(async()=>({close:vi.fn()})))
})
it("blocks unsupported browsers rather than falling back to timed photos",()=>{
 vi.stubGlobal("Worker",undefined)
 expect(()=>new PoseDetector()).toThrow(/current Chrome or Safari/)
})
it("analyzes an unmirrored snapshot and saves that same snapshot mirrored",async()=>{
 const context={drawImage:vi.fn(),translate:vi.fn(),scale:vi.fn()}
 vi.spyOn(HTMLCanvasElement.prototype,"getContext").mockReturnValue(context as unknown as CanvasRenderingContext2D)
 vi.spyOn(HTMLCanvasElement.prototype,"toDataURL").mockReturnValue("data:image/jpeg;base64,checked")
 const detector=new PoseDetector();await detector.init()
 const source=video()
 const sample=await detector.sample(source)
 expect(sample?.observation.yaw).toBe(25)
 expect(context.scale).not.toHaveBeenCalled()
 expect(sample?.photo()).toContain("checked")
 expect(context.scale).toHaveBeenCalledWith(-1,1)
 const draws=context.drawImage.mock.calls
 expect(draws[0][0]).toBe(source)
 expect(draws[1][0]).toBeInstanceOf(HTMLCanvasElement)
 expect(draws[1][0]).not.toBe(source)
 expect(await detector.sample(source)).toBeNull() // same camera timestamp cannot count twice
 detector.close();expect(worker.terminate).toHaveBeenCalled()
})
it("refuses paused or unreadable video",async()=>{
 const detector=new PoseDetector()
 const source=video();Object.defineProperty(source,"paused",{value:true})
 expect(await detector.sample(source)).toBeNull()
 expect(createImageBitmap).not.toHaveBeenCalled()
 detector.close()
})
it("closing the worker rejects outstanding work and releases the worker",async()=>{
 const detector=new PoseDetector()
 worker.postMessage.mockImplementation(()=>{})
 const promise=detector.init()
 detector.close()
 await expect(promise).rejects.toThrow(/closed/)
 expect(worker.terminate).toHaveBeenCalled()
})
