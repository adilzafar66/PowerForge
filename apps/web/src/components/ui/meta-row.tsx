import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export function MetaRow({
  label,
  children,
  className,
}: {
  label: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex gap-5 px-5 py-3.5", className)}>
      <span className="w-24 shrink-0 pt-0.5 text-[12px] font-semibold uppercase tracking-wide text-slate-400">
        {label}
      </span>
      <div className="flex-1 text-[13.5px] leading-relaxed text-slate-700">{children}</div>
    </div>
  );
}
