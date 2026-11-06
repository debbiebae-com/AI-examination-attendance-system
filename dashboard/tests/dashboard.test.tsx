import React from "react";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";
import { Dashboard } from "@/components/dashboard";
import { demoFeed } from "@/lib/demo";

beforeEach(()=>{
  vi.stubGlobal("fetch",vi.fn(async(path: string)=>({ok:true,json:async()=>path.includes("students")?[]:{session_id:null,status:"idle",events:[],unidentified_now:0,present_count:0}})));
});
it("shows real idle state, not fabricated students or a running camera",async()=>{
  render(<Dashboard/>);
  expect(await screen.findByText("No active session")).toBeInTheDocument();
  expect(screen.queryByText("Kwame Mensah")).not.toBeInTheDocument();
  expect(screen.getByRole("button",{name:"Export attendance"})).toBeDisabled();
});
it("offers an explicit illustration, search, student details and exit",async()=>{
  const user=userEvent.setup(); render(<Dashboard/>);
  await screen.findByText("No active session");
  await user.click(screen.getByRole("button",{name:"Preview layout"}));
  expect(screen.getByText("Illustrative preview.")).toBeInTheDocument();
  await user.type(screen.getByRole("textbox",{name:"Search students"}),"PS/CSC/24/0016");
  expect(screen.getAllByRole("row")).toHaveLength(2);
  await user.click(screen.getByRole("button",{name:"View Kwame Mensah"}));
  const panel=screen.getByRole("dialog");
  expect(within(panel).getByText("PS/CSC/24/0016")).toBeInTheDocument();
  expect(within(panel).getByText("Not supplied")).toBeInTheDocument();
  await user.keyboard("{Escape}");
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  await user.click(screen.getByRole("button",{name:"Exit preview"}));
  await screen.findByText("No active session");
  expect(screen.queryByText("Illustrative preview.")).not.toBeInTheDocument();
});
it("shows a disconnected alert when the local API is unavailable",async()=>{
  vi.stubGlobal("fetch",vi.fn(async()=>({ok:false,status:503})));
  render(<Dashboard/>);
  expect(await screen.findByRole("alert")).toHaveTextContent("Local API is offline");
  expect(screen.getByText("API disconnected")).toBeInTheDocument();
  expect(screen.getByRole("button",{name:"Export attendance"})).toBeDisabled();
});
it("renders actual API records and differentiates identity from attendance",async()=>{
  const fixture=demoFeed(); fixture.session.session_id="live-test"; fixture.attendance.pop(); fixture.session.present_count=3;
  vi.stubGlobal("fetch",vi.fn(async(path:string)=>({ok:true,json:async()=>path.includes("live/session")?fixture.session:path.includes("students")?fixture.students:fixture.attendance})));
  render(<Dashboard/>);
  await screen.findByText("Camera active");
  expect(screen.getByText("Not recorded")).toBeInTheDocument();
  expect(screen.getAllByRole("row")).toHaveLength(5);
  expect(screen.queryByText("Illustrative preview.")).not.toBeInTheDocument();
  expect(screen.getByRole("button",{name:"Export attendance"})).toBeEnabled();
});
