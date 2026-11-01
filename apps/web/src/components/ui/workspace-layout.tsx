import type { HTMLAttributes } from "react";
import { cn } from "@/lib/utils";
export function WorkspaceRoot({
  className,
  ...props
}: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      {...props}
      className={cn("text-ink text-workspace-body leading-[normal]", className)}
    />
  );
}
export function WorkspaceContent({
  className,
  ...props
}: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      {...props}
      className={cn(
        "w-full max-w-[var(--pf-workspace-content-max)] pt-[27px] px-[max(34px,_4%)] pb-16 m-auto animate-[workspace-appear_var(--pf-motion-content)_ease-out] max-[1120px]:pt-[22px] max-[1120px]:px-[30px] max-[1120px]:pb-[50px] max-[790px]:p-5 max-[530px]:p-[18px] motion-reduce:animate-none",
        className,
      )}
    />
  );
}
export function WorkspaceColumns({
  variant = "revision",
  className,
  ...props
}: HTMLAttributes<HTMLDivElement> & {
  variant?: "project" | "revision" | "form";
}) {
  return (
    <div
      {...props}
      className={cn(
        "grid grid-cols-[minmax(0,_1fr)_var(--pf-workspace-rail)] gap-5 items-start max-[1120px]:grid-cols-[1fr]",
        variant === "project" &&
          "max-[1120px]:grid-cols-[1fr] grid-cols-[minmax(0,_1fr)_var(--pf-workspace-project-rail)]",
        variant === "form" &&
          "grid grid-cols-[minmax(0,_1fr)_var(--pf-workspace-form-rail)] items-start gap-5 max-[1120px]:grid-cols-[1fr]",
        className,
      )}
    />
  );
}
export function WorkspaceNote({
  as: Element = "p",
  className,
  ...props
}: HTMLAttributes<HTMLElement> & { as?: "p" | "div" }) {
  return (
    <Element
      {...props}
      className={cn(
        "py-[13px] px-[15px] text-muted border border-border rounded-[var(--pf-radius-control)] bg-[var(--pf-surface-note)] text-workspace-label leading-[var(--pf-leading-copy)]",
        className,
      )}
    />
  );
}
