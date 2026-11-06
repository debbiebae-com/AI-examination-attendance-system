import type { Feed } from "./data";
export function demoFeed(): Feed {
  const at = new Date().toISOString();
  const students = [
    {student_no:"PS/CSC/24/0016",full_name:"Kwame Mensah",programme:"BSc Computer Science",level:200,has_photo:false,face_samples:9},
    {student_no:"PS/ITC/23/0042",full_name:"Ama Osei",programme:"BSc Information Technology",level:300,has_photo:false,face_samples:9},
    {student_no:"PS/CSC/24/0028",full_name:"Abena Owusu",programme:"BSc Computer Science",level:200,has_photo:false,face_samples:9},
    {student_no:"PS/CSC/24/0031",full_name:"Kofi Asante",programme:"BSc Computer Science",level:200,has_photo:false,face_samples:9},
  ];
  // Explicitly fictional fixture metadata, reflecting the server's agreed demo rules.
  const illustrated = students.map(student=>({...student,presentation:{
    department:student.student_no.includes("/CSC/")?"Computer Science and Information Technology":null,
    programme:student.programme,level:student.student_no.includes("/24/")?300:student.level,
    index_programme_code:student.student_no.split("/")[1],index_year_code:student.student_no.split("/")[2],
    department_source:student.student_no.includes("/CSC/")?"demo_index_rule":"not_supplied",
    level_source:student.student_no.includes("/24/")?"demo_index_rule":"local_record",is_demo_metadata:true,
  }}));
  return {students:illustrated,attendance:students.map(s=>({student_no:s.student_no,full_name:s.full_name,recorded_at:at,confidence:0.68,source:"camera"})),session:{
    session_id:"illustration-only",status:"running",exam:{id:1,course_code:"CSC 204",course_title:"Data Structures & Algorithms",hall:"Main Examination Hall · Block A",starts_at:"2026-11-10T09:00:00Z",ends_at:"2026-11-10T11:00:00Z"},started_at:at,updated_at:at,identified_count:4,unidentified_now:1,visible_faces:2,processed_fps:12.4,processing_ms:80.6,present_count:4,
    events:students.flatMap((s,i)=>[{id:i*2+1,at,kind:"identified",student_no:s.student_no,track_id:i+1},{id:i*2+2,at,kind:"present",student_no:s.student_no,track_id:i+1}]).concat([{id:9,at,kind:"unknown",student_no:"",track_id:5}]),
  }};
}
