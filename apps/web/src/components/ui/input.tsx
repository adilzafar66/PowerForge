import * as React from "react";

import { cn } from "@/lib/utils";

const fieldClassName =
  "flex w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-[13.5px] text-slate-800 shadow-[0_1px_2px_rgba(0,0,0,0.04)] transition-all placeholder:text-slate-300 focus-visible:border-blue-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500/40 disabled:cursor-not-allowed disabled:opacity-50";

const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, type, ...props }, ref) => (
    <input type={type} className={cn(fieldClassName, "h-auto", className)} ref={ref} {...props} />
  ),
);
Input.displayName = "Input";

const Textarea = React.forwardRef<
  HTMLTextAreaElement,
  React.TextareaHTMLAttributes<HTMLTextAreaElement>
>(({ className, ...props }, ref) => (
  <textarea className={cn(fieldClassName, "resize-none", className)} ref={ref} {...props} />
));
Textarea.displayName = "Textarea";

export { Input, Textarea, fieldClassName };
