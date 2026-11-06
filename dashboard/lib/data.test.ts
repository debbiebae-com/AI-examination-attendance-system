import { describe, it, expect } from "vitest";
import { academic, csv, visibleStudents, time, statusLabel, eventLabel } from "./data";
import { demoFeed } from "./demo";

describe("dashboard data", ()=>{
  it("keeps fictional data explicit and separate from live requests", ()=>{
    const feed=demoFeed();
    expect(feed.session.session_id).toBe("illustration-only");
    expect(feed.session.present_count).toBe(feed.attendance.length);
  });
  it("searches real identities by long index, name and programme", ()=>{
    const feed=demoFeed();
    expect(visibleStudents(feed,"PS/CSC/24/0016")[0].full_name).toBe("Kwame Mensah");
    expect(visibleStudents(feed,"ama osei")).toHaveLength(1);
    expect(visibleStudents(feed,"unknown")).toHaveLength(0);
  });
  it("includes identified people even if attendance was refused", ()=>{
    const feed=demoFeed(); feed.attendance=[];
    expect(visibleStudents(feed,"")).toHaveLength(4);
  });
  it("does not label every enrolled student as recognized", ()=>{
    const feed=demoFeed(); feed.attendance=[]; feed.session.events=[];
    expect(visibleStudents(feed,"")).toHaveLength(0);
  });
  it("exports records with quoted commas and spreadsheet protection", ()=>{
    const feed=demoFeed(); feed.attendance[0].full_name='=SUM(1,2)"';
    const output=csv(feed.attendance,feed.session.exam);
    expect(output).toContain('"\'=SUM(1,2)"""');
    expect(output).toContain("Similarity (not probability)");
    expect(output).not.toContain("embedding");
  });
  it("formats timezone-naive database times as Ghana UTC", ()=>{
    expect(time("2026-11-10T09:15:30")).toBe("09:15:30");
    expect(time()).toBe("—");
  });
  it("distinguishes disconnected, stopped, and not-recorded states", ()=>{
    expect(statusLabel("disconnected")).toBe("Worker disconnected");
    expect(statusLabel("stopped")).toBe("Session stopped");
    expect(eventLabel("not_eligible")).toBe("Attendance not recorded");
  });
});


it("uses presentation metadata without mutating the recorded level",()=>{
 const student=demoFeed().students[0];
 expect(student.level).toBe(200);
 expect(academic(student).level).toBe(300);
 expect(academic(student).department).toBe("Computer Science and Information Technology");
 expect(visibleStudents(demoFeed(),"300")).toHaveLength(4);
});
it("falls back honestly when an older API supplies no presentation data",()=>{
 const student={...demoFeed().students[0],presentation:undefined};
 expect(academic(student).level).toBe(student.level);
 expect(academic(student).department).toBeNull();
});
