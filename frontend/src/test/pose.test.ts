import { describe, expect, it } from "vitest"
import { angles, checkPose, PoseGate } from "@/lib/pose"
const good={faces:1,yaw:0,pitch:0,roll:0,width:0.4,height:0.5,cx:0.5,cy:0.5}
function matrix(yaw:number) {
 const a=yaw*Math.PI/180,c=Math.cos(a),s=Math.sin(a)
 return [c,0,-s,0,0,1,0,0,s,0,c,0,0,0,-50,1]
}
describe("head pose direction and quality",()=>{
 it("uses column-major rotation and the person's own left/right on unmirrored input",()=>{
  expect(angles(matrix(25))?.yaw).toBeCloseTo(25)
  expect(checkPose({...good,...angles(matrix(25))},"left").valid).toBe(true)
  expect(checkPose({...good,...angles(matrix(-25))},"right").valid).toBe(true)
  expect(checkPose({...good,yaw:-25},"left").message).toContain("That's your RIGHT")
 })
 it("does not accept a forward face for either turn",()=>{
  expect(checkPose(good,"straight").valid).toBe(true)
  expect(checkPose(good,"left").valid).toBe(false)
  expect(checkPose(good,"right").valid).toBe(false)
 })
 it.each([
  {faces:0},{faces:2},{yaw:NaN},{yaw:undefined},{width:0.1},{width:0.95},
  {height:0.95},{cx:0.1},{cy:0.9},{pitch:30},{roll:30},{yaw:60},
 ])("rejects unusable observation %j",overrides=>{
  expect(checkPose({...good,...overrides},"straight").valid).toBe(false)
 })
 it("does not interpret a missing/invalid matrix as a straight pose",()=>{
  expect(angles([])).toBeNull()
  expect(angles(Array(16).fill(0))).toBeNull()
  expect(angles(Array(16).fill(NaN))).toBeNull()
 })
})
describe("stable pose gate",()=>{
 it("requires sustained valid observations, not a timer alone",()=>{
  const gate=new PoseGate()
  expect(gate.observe(true,0).ready).toBe(false)
  expect(gate.observe(true,300).ready).toBe(false)
  expect(gate.observe(true,600).ready).toBe(true)
 })
 it("resets stability when the pose or face becomes invalid",()=>{
  const gate=new PoseGate()
  gate.observe(true,0);gate.observe(true,300);gate.observe(false,500)
  expect(gate.observe(true,700).ready).toBe(false)
 })
 it("does not count a frozen/long-gap feed as a continuous hold",()=>{
  const gate=new PoseGate()
  gate.observe(true,0);gate.observe(true,300)
  expect(gate.observe(true,1800)).toEqual({ready:false,held:0})
 })
})
