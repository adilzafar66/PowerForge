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

export function EvidencePagination({ page, onChange }: {
  page: { total: number; previous_cursor: string | null; next_cursor: string | null };
  onChange: (cursor: string) => void;
}) {
  if (!page.previous_cursor && !page.next_cursor) return null;
  return (
    <nav aria-label="Result pages" className="flex flex-wrap items-center justify-between gap-1.5 text-workspace-caption text-muted">
      <button type="button" className={docButtonClass("tiny")} disabled={!page.previous_cursor} onClick={() => onChange(page.previous_cursor!)}>Previous</button>
      <span>{page.total} results</span>
      <button type="button" className={docButtonClass("tiny")} disabled={!page.next_cursor} onClick={() => onChange(page.next_cursor!)}>Next</button>
    </nav>
  );
}
