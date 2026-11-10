import type { ReactNode } from "react";

import { docButtonClass } from "@/components/documents-ui";
import { cn } from "@/lib/utils";

const card = "rounded-[var(--pf-radius-control)] border border-border bg-panel";

export function readableKey(value: string) {
  return value.toLowerCase().replaceAll("_", " ").replace(/^./, (letter) => letter.toUpperCase());
}

export function PanelMessage({ children, error, retry }: { children: ReactNode; error?: boolean; retry?: () => void }) {
  return (
    <div role={error ? "alert" : undefined} className={cn(card, "p-3 text-workspace-caption leading-relaxed", error ? "text-danger" : "text-muted")}>
      {children}
      {retry && <button type="button" className={cn(docButtonClass("tiny"), "mt-2 flex")} onClick={retry}>Try again</button>}
    </div>
  );
}

export function EvidencePagination({ total, size, start, onChange }: { total: number; size: number; start: number; onChange: (start: number) => void }) {
  if (total <= size && start === 0) return null;
  return (
    <nav aria-label="Result pages" className="flex flex-wrap items-center justify-between gap-1.5 text-workspace-caption text-muted">
      <button type="button" className={docButtonClass("tiny")} disabled={!start} onClick={() => onChange(Math.max(0, start - size))}>Previous</button>
      <span>{Math.min(total, start + 1)}–{Math.min(total, start + size)} of {total}</span>
      <button type="button" className={docButtonClass("tiny")} disabled={start + size >= total} onClick={() => onChange(start + size)}>Next</button>
    </nav>
  );
}
