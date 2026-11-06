"use client";
import * as React from "react";
import { Dialog as Primitive } from "radix-ui";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";
export const Dialog = Primitive.Root;
export const DialogTitle = Primitive.Title;
export const DialogDescription = Primitive.Description;
export function DialogContent({className,children,...props}: React.ComponentProps<typeof Primitive.Content>) {
 return <Primitive.Portal><Primitive.Overlay className="fixed inset-0 z-40 bg-slate-950/35 backdrop-blur-[3px]"/><Primitive.Content className={cn("fixed right-0 top-0 z-50 h-dvh w-full max-w-md overflow-y-auto bg-white p-8 shadow-2xl outline-none",className)} {...props}>{children}<Primitive.Close className="absolute right-5 top-5 rounded-md p-2 text-slate-500 hover:bg-slate-100 focus-visible:ring-2 focus-visible:ring-emerald-600"><X className="size-5"/><span className="sr-only">Close student details</span></Primitive.Close></Primitive.Content></Primitive.Portal>;
}
