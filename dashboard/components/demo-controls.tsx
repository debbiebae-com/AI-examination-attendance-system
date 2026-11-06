"use client";
import { useEffect, useState } from "react";
import { Camera, Download, Settings2, Square, Trash2, UserRoundCheck, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import type { Exam } from "@/lib/data";

type Job = {running:boolean;kind:string|null;exit_code:number|null;log:string[];sync_configured:boolean};
type Person = {student_no:string;full_name:string;face_samples:number;registered:boolean;ready:boolean;reasons:string[]};
type Plan = {token:string;students:{student_no:string;full_name:string}[];counts:{embeddings:number;registrations:number;attendance:number};warning:string};
async function api<T>(path:string, body?:unknown):Promise<T> {
 const response=await fetch(`/api/${path}`,{method:body===undefined?"GET":"POST",headers:body===undefined?undefined:{"Content-Type":"application/json"},body:body===undefined?undefined:JSON.stringify(body),cache:"no-store",signal:AbortSignal.timeout(8000)});
 const data=await response.json();
 if(!response.ok) throw new Error(typeof data.detail==="string"?data.detail:"Request failed. Refresh and try again.");
 return data;
}
export function DemoControls({disabled=false,onChanged}:{disabled?:boolean;onChanged:()=>void}) {
 const [open,setOpen]=useState(false);
 const [exams,setExams]=useState<Exam[]>([]);
 const [exam,setExam]=useState("");
 const [people,setPeople]=useState<Person[]>([]);
 const [selected,setSelected]=useState<string[]>([]);
 const [job,setJob]=useState<Job|null>(null);
 const [error,setError]=useState("");
 const [loadError,setLoadError]=useState("");
 const [notice,setNotice]=useState("");
 const [busy,setBusy]=useState(false);
 const [ready,setReady]=useState(false);
 const [camera,setCamera]=useState("0");
 const [query,setQuery]=useState("");
 const [plan,setPlan]=useState<Plan|null>(null);
 const [confirmation,setConfirmation]=useState("");
 const [refresh,setRefresh]=useState(0);
 useEffect(()=>{
   if(!open || disabled) return;
   let cancelled=false;
   let timer: ReturnType<typeof setTimeout>;
   setReady(false); setPeople([]); setSelected([]); setPlan(null);
   async function poll() {
     try {
       const [status,list]=await Promise.all([api<Job>("control/status"),api<Exam[]>("exams")]);
       const chosen=exam || String(list[0]?.id || "");
       const roster=chosen?await api<Person[]>(`control/readiness?exam_id=${chosen}`):[];
       if(cancelled)return;
       setJob(status);setExams(list);setPeople(roster);setReady(true);setLoadError("");
       if(!exam && chosen)setExam(chosen);
     }catch(e){if(!cancelled){setLoadError(e instanceof Error?e.message:"Controls unavailable");setReady(false);}}
     finally{if(!cancelled)timer=setTimeout(poll,2000);}
   }
   poll();return()=>{cancelled=true;clearTimeout(timer);};
 },[open,exam,disabled,refresh]);
 async function run(path:string,body:unknown) {
   setBusy(true);setError("");setNotice("");
   try {
     const result=await api<{message?:string}>(`control/${path}`,body);
     setNotice(result.message || "Task started. Progress appears below.");
     setPlan(null);setConfirmation("");setSelected([]);setRefresh(r=>r+1);onChanged();
   }catch(e){setError(e instanceof Error?e.message:"Operation failed");}
   finally{setBusy(false);}
 }
 async function preview(numbers:string[]) {
   setBusy(true);setError("");setNotice("");setPlan(null);setConfirmation("");
   try{setPlan(await api<Plan>("control/delete/preview",{student_nos:numbers}));}
   catch(e){setError(e instanceof Error?e.message:"Preview failed");}
   finally{setBusy(false);}
 }
 const locked=busy || !ready || !!job?.running;
 const shown=people.filter(p=>`${p.full_name} ${p.student_no}`.toLowerCase().includes(query.toLowerCase()));
 return <>
  <Button variant="outline" disabled={disabled} onClick={()=>setOpen(true)} className="h-9 bg-white text-xs shadow-none"><Settings2/>Demo controls</Button>
  <Dialog open={open} onOpenChange={value=>{setOpen(value);if(!value){setPlan(null);setConfirmation("");}}}><DialogContent className="max-w-3xl">
   <DialogTitle className="text-xl font-semibold">Demo controls</DialogTitle>
   <DialogDescription className="mt-2 max-w-xl text-xs leading-5 text-slate-500">Operate this PC’s demonstration. Changes affect your real local database, not layout preview data. Stop recognition before syncing, registering or removing volunteers.</DialogDescription>
   {(error||loadError)&&<div role="alert" className="mt-4 rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-900">{error||loadError}</div>}
   {notice&&<p role="status" className="mt-4 rounded-lg bg-emerald-50 p-3 text-xs text-emerald-900">{notice}</p>}
   <div className="mt-6 grid gap-4 sm:grid-cols-[1fr_120px]">
    <label className="space-y-2 text-xs font-medium">Examination<select aria-label="Control examination" value={exam} disabled={busy||job?.running} onChange={e=>{setExam(e.target.value);setPlan(null);setSelected([]);}} className="h-10 w-full rounded-md border bg-white px-3 text-xs"><option value="">Choose an examination</option>{exams.map(e=><option key={e.id} value={e.id}>{e.course_code} · {e.course_title}</option>)}</select></label>
    <label className="space-y-2 text-xs font-medium">Camera number<Input aria-label="Camera number" type="number" min={0} max={10} value={camera} disabled={locked} onChange={e=>setCamera(e.target.value)}/></label>
   </div>
   <div className="mt-4 flex flex-wrap gap-2">
    <Button className="bg-emerald-800 hover:bg-emerald-900" disabled={locked||!exam||camera===""||!Number.isInteger(Number(camera))||Number(camera)<0||Number(camera)>10} onClick={()=>run("camera/start",{exam_id:Number(exam),camera:Number(camera)})}><Camera/>Start recognition</Button>
    <Button variant="outline" disabled={busy||!ready||!job?.running||job.kind!=="camera"} onClick={()=>run("camera/stop",{})}><Square/>Stop camera</Button>
    <Button variant="outline" disabled={locked||!exam||!job?.sync_configured} onClick={()=>run("sync",{exam_id:Number(exam)})}><Download/>Sync submissions</Button>
   </div>
   <p className="mt-3 text-[11px] leading-5 text-slate-500">{job?.sync_configured?"Sync imports pending phone submissions and wipes cloud photos after successful sync. It uses each submission’s exam, falling back to the exam selected above.":"Sync needs SUPABASE_URL and SUPABASE_SERVICE_KEY configured on the backend PC once. Never enter the service key in the browser."} Recognition opens the PC camera window; results flow into the live dashboard.</p>
   <div className="mt-5 rounded-lg border bg-slate-50 p-3"><p className="text-xs font-medium">{job?.running?`${job.kind==="camera"?"Recognition":"Sync"} task running`:job?.kind?`${job.kind} finished · exit ${job.exit_code??"pending"}`:"No dashboard task running"}</p><p className="mt-1 text-[10px] text-slate-500">Stop is cooperative: allow the current frame/model loading to finish. For a camera started in a terminal, press q in that camera window instead.</p>{!!job?.log.length&&<pre aria-label="Demo task output" className="mt-3 max-h-36 overflow-auto whitespace-pre-wrap break-all text-[10px] leading-4 text-slate-600">{job.log.join("\n")}</pre>}</div>
   <section className="mt-7 border-t pt-6"><div className="flex flex-wrap items-center justify-between gap-3"><div><h3 className="text-sm font-semibold">Demo volunteers</h3><p className="mt-1 text-[11px] text-slate-500">{selected.length} selected · {people.length} stored locally</p></div><Button size="sm" variant="outline" disabled={busy} onClick={()=>setRefresh(r=>r+1)}><RefreshCw/>Refresh</Button></div>
    <Input aria-label="Search volunteers" placeholder="Search name or index number" value={query} onChange={e=>setQuery(e.target.value)} className="mt-4"/>
    <div className="mt-3 max-h-64 overflow-auto rounded-lg border"><table className="w-full text-left text-xs"><thead className="sticky top-0 bg-slate-50 text-[10px] text-slate-500"><tr><th className="p-3"><input type="checkbox" aria-label="Select all visible volunteers" disabled={locked||!shown.length} checked={!!shown.length&&shown.every(p=>selected.includes(p.student_no))} onChange={e=>{setPlan(null);setSelected(e.target.checked?[...new Set([...selected,...shown.map(p=>p.student_no)])]:selected.filter(n=>!shown.some(p=>p.student_no===n)));}}/></th><th className="p-3">Volunteer</th><th className="p-3">Face samples</th><th className="p-3">Readiness</th></tr></thead><tbody>{shown.map(p=><tr key={p.student_no} className="border-t"><td className="p-3"><input type="checkbox" aria-label={`Select ${p.full_name}`} checked={selected.includes(p.student_no)} disabled={locked} onChange={e=>{setPlan(null);setSelected(e.target.checked?[...selected,p.student_no]:selected.filter(n=>n!==p.student_no));}}/></td><td className="p-3"><span className="font-medium">{p.full_name}</span><span className="mt-1 block text-[10px] text-slate-500">{p.student_no}</span></td><td className="p-3">{p.face_samples}</td><td className="p-3"><span className={p.ready?"text-emerald-700":"text-amber-800"}>{p.ready?"Ready":p.reasons.join(" · ")}</span></td></tr>)}</tbody></table>{!shown.length&&<p className="p-5 text-center text-xs text-slate-500">{ready?"No matching volunteers. Sync phone submissions to add them.":"Loading volunteer readiness…"}</p>}</div>
    <div className="mt-4 flex flex-wrap gap-2"><Button size="sm" variant="outline" disabled={locked||!exam||!selected.length} onClick={()=>run("register",{exam_id:Number(exam),student_nos:selected})}><UserRoundCheck/>Register selected</Button><Button size="sm" variant="outline" disabled={locked||!selected.length} onClick={()=>preview(selected)}><Trash2/>Remove selected…</Button><Button size="sm" variant="outline" disabled={locked||!selected.length||selected.length===people.length} onClick={()=>preview(people.filter(p=>!selected.includes(p.student_no)).map(p=>p.student_no))}>Keep only selected…</Button></div>
    <p className="mt-3 text-[10px] leading-5 text-slate-500">Registration does not change fee/suspension flags. Removal deletes local students, face embeddings, registrations and attendance. Exams and Supabase inbox submissions are preserved.</p>
   </section>
   {plan&&<section aria-label="Confirm local deletion" className="mt-6 rounded-xl border border-red-200 bg-red-50 p-5"><h3 className="text-sm font-semibold text-red-900">Review deletion: {plan.students.length} student(s)</h3><ul className="mt-3 max-h-32 overflow-auto text-xs text-red-900">{plan.students.map(p=><li key={p.student_no} className="py-1">{p.full_name} · {p.student_no}</li>)}</ul><p className="mt-3 text-xs leading-5 text-red-900">Also removes {plan.counts.embeddings} face samples, {plan.counts.registrations} registrations and {plan.counts.attendance} attendance records. This cannot be undone.</p><p className="mt-2 text-[11px] leading-5 text-red-800">{plan.warning} Preview expires after two minutes.</p><label className="mt-4 block text-xs font-medium text-red-900">Type DELETE to confirm<Input aria-label="Deletion confirmation" className="mt-2 bg-white" value={confirmation} onChange={e=>setConfirmation(e.target.value)}/></label><div className="mt-3 flex gap-2"><Button variant="destructive" disabled={busy||!ready||job?.running||confirmation!=="DELETE"} onClick={()=>run("delete/confirm",{token:plan.token,confirmation})}>Permanently remove</Button><Button variant="outline" disabled={busy} onClick={()=>{setPlan(null);setConfirmation("");}}>Cancel</Button></div></section>}
  </DialogContent></Dialog>
 </>;
}
