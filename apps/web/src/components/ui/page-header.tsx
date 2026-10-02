import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export function PageHeader({
  title,
  description,
  actions,
  className,
}: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("mb-7 flex items-center justify-between gap-4", className)}>
      <div>
        <h1 className="text-[21px] font-bold tracking-tight text-slate-900">{title}</h1>
        {description ? (
          <p className="mt-0.5 text-[13px] text-slate-400">{description}</p>
        ) : null}
      </div>
      {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
    </div>
  );
}
