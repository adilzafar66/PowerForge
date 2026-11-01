import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";
type Variant = { variant?: "projects" | "revisions" };
export function RegisterTable({
  className,
  ...props
}: ComponentProps<"table">) {
  return (
    <table
      {...props}
      className={cn(
        "w-full border-collapse text-left max-[790px]:min-w-[650px]",
        className,
      )}
    />
  );
}
export function RegisterHeader({
  variant = "revisions",
  className,
  ...props
}: ComponentProps<"th"> & Variant) {
  return (
    <th
      {...props}
      className={cn(
        "bg-[var(--pf-table-heading)] text-workspace-overline text-[var(--pf-text-tertiary)] tracking-[0.7px] uppercase font-bold py-[14px] px-[17px] whitespace-nowrap max-[790px]:py-3 max-[790px]:px-[10px]",
        variant === "projects" &&
          "max-[790px]:py-3 max-[790px]:px-[10px] py-[17px] px-[18px]",
        className,
      )}
    />
  );
}
export function RegisterCell({
  variant = "revisions",
  className,
  ...props
}: ComponentProps<"td"> & Variant) {
  return (
    <td
      {...props}
      className={cn(
        "py-[15px] px-[17px] border-t border-[var(--pf-border-row)] text-workspace-body align-middle max-[790px]:py-3 max-[790px]:px-[10px]",
        variant === "projects" &&
          "max-[790px]:py-3 max-[790px]:px-[10px] p-[18px] text-muted",
        className,
      )}
    />
  );
}
export function RegisterRow({ className, ...props }: ComponentProps<"tr">) {
  return (
    <tr
      {...props}
      className={cn(
        "cursor-pointer [transition:background_var(--pf-transition-fast)] hover:bg-[var(--pf-table-row-hover)] focus-visible:[outline:2px_solid_var(--pf-action)] focus-visible:[outline-offset:-2px] focus-visible:bg-selection",
        className,
      )}
    />
  );
}
export function RegisterToolbar({
  className,
  ...props
}: ComponentProps<"div">) {
  return (
    <div
      {...props}
      className={cn(
        "flex gap-3 justify-between items-center flex-wrap py-[17px] px-[19px] border-b border-border",
        className,
      )}
    />
  );
}
export function RegisterFooter({ className, ...props }: ComponentProps<"div">) {
  return (
    <div
      {...props}
      className={cn(
        "border-t border-border py-[14px] px-[19px] text-muted text-workspace-caption flex justify-between gap-[10px]",
        className,
      )}
    />
  );
}
