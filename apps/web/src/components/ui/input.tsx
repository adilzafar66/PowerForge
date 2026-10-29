import * as React from "react";

import { cn } from "@/lib/utils";

const fieldClassName =
  "flex w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-[13.5px] text-slate-800 transition-colors placeholder:text-muted focus-visible:border-focus focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus/30 aria-invalid:border-danger disabled:cursor-not-allowed disabled:opacity-50";

const Input = React.forwardRef<
  HTMLInputElement,
  React.InputHTMLAttributes<HTMLInputElement>
>(({ className, type, ...props }, ref) => (
  <input
    type={type}
    className={cn(fieldClassName, "min-h-10", className)}
    ref={ref}
    {...props}
  />
));
Input.displayName = "Input";

const Textarea = React.forwardRef<
  HTMLTextAreaElement,
  React.TextareaHTMLAttributes<HTMLTextAreaElement>
>(({ className, ...props }, ref) => (
  <textarea
    className={cn(fieldClassName, "resize-none", className)}
    ref={ref}
    {...props}
  />
));
Textarea.displayName = "Textarea";

export { Input, Textarea, fieldClassName };
