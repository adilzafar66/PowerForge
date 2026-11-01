import * as React from "react";

import { cn } from "@/lib/utils";

const fieldClassName =
  "flex w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-[13.5px] text-slate-800 transition-colors placeholder:text-muted focus-visible:border-focus focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus/30 aria-invalid:border-danger disabled:cursor-not-allowed disabled:opacity-50";

export type ControlPresentation = "default" | "workspace";
/** Shared control surface; focus and invalid borders preserve the approved workspace treatment. */
export const workspaceControlClassName =
  "min-h-[var(--pf-control-height-input)] border border-border rounded-[var(--pf-radius-control)] py-[10px] px-3 text-workspace-label text-ink focus-visible:border-border aria-invalid:border-border";
const Input = React.forwardRef<
  HTMLInputElement,
  React.InputHTMLAttributes<HTMLInputElement> & {
    presentation?: ControlPresentation;
  }
>(({ className, type, presentation = "default", ...props }, ref) => (
  <input
    type={type}
    className={cn(
      fieldClassName,
      "min-h-10",
      presentation === "workspace" && workspaceControlClassName,
      className,
    )}
    ref={ref}
    {...props}
  />
));
Input.displayName = "Input";

const Textarea = React.forwardRef<
  HTMLTextAreaElement,
  React.TextareaHTMLAttributes<HTMLTextAreaElement> & {
    presentation?:
      "default" | "workspace" | "workspace-create" | "workspace-editor";
  }
>(({ className, presentation = "default", ...props }, ref) => (
  <textarea
    className={cn(
      fieldClassName,
      "resize-none",
      presentation !== "default" && [
        workspaceControlClassName,
        "resize-y",
        presentation === "workspace-create" ? "min-h-[91px]" : "min-h-[106px]",
      ],
      className,
    )}
    ref={ref}
    {...props}
  />
));
Textarea.displayName = "Textarea";

export { Input, Textarea, fieldClassName };
