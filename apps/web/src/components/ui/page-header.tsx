import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export function PageHeader({
  title,
  presentation = "default",
  description,
  actions,
  className,
}: {
  title: ReactNode;
  presentation?: "default" | "workspace";
  description?: ReactNode;
  actions?: ReactNode;
  className?: string;
}) {
  if (presentation === "workspace")
    return (
      <header
        className={cn(
          "py-8 px-[max(34px,_4%)] bg-panel border-b border-border max-[1120px]:py-[25px] max-[1120px]:px-[30px] max-[790px]:p-[22px] max-[530px]:p-[18px]",
          className,
        )}
      >
        <div className="max-w-[var(--pf-workspace-header-max)] m-auto flex items-center justify-between gap-5 max-[790px]:items-start max-[790px]:flex-col">
          <div>
            <h1 className="text-workspace-title leading-[1.2] tracking-[-0.025em] font-bold mt-0 mx-0 mb-[6px] flex items-center gap-[10px] flex-wrap max-[530px]:text-workspace-title-mobile">
              {title}
            </h1>
            <p className="text-workspace-body text-muted leading-[var(--pf-leading-copy)] m-0">
              {description}
            </p>
          </div>
          <div className="flex items-center gap-[10px] flex-wrap">
            {actions}
          </div>
        </div>
      </header>
    );
  return (
    <div
      className={cn(
        "mb-7 flex flex-wrap items-center justify-between gap-4",
        className,
      )}
    >
      <div>
        <h1 className="text-[29px] font-bold tracking-tight text-slate-900">
          {title}
        </h1>
        {description ? (
          <p className="mt-0.5 text-[13px] text-slate-400">{description}</p>
        ) : null}
      </div>
      {actions ? (
        <div className="flex shrink-0 items-center gap-2">{actions}</div>
      ) : null}
    </div>
  );
}
