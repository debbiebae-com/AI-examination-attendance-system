"use client";
import * as React from "react";
import { Dialog as Primitive } from "radix-ui";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";
export const Dialog = Primitive.Root;
export const DialogTitle = Primitive.Title;
export const DialogDescription = Primitive.Description;
export function DialogContent({className,children,...props}: React.ComponentProps<typeof Primitive.Content>) {
 return <Primitive.Portal><Primitive.Overlay className="fixed inset-0 z-40 bg-black/40"/><Primitive.Content className={cn("fixed right-0 top-0 z-50 h-dvh w-full max-w-md overflow-y-auto border-l bg-background p-6 shadow-lg sm:p-8 outline-none",className)} {...props}>{children}<Primitive.Close className="absolute right-5 top-5 rounded-md p-2 text-muted-foreground hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring"><X className="size-5"/><span className="sr-only">Close panel</span></Primitive.Close></Primitive.Content></Primitive.Portal>;
}
