import { Archive, Circle } from "lucide-react";
import { cn } from "@/lib/utils";

/** Shared presentation for tables within a revision, based on the Documents table. */
export const revisionTable = {
  table: "block w-full text-[13px] md:table",
  head: "hidden md:table-header-group",
  headerRow: "border-b border-border bg-soft",
  header:
    "px-4 py-3 text-left text-[11px] font-semibold tracking-wide text-muted uppercase",
  primaryCell: "block px-0 py-0 md:table-cell md:px-5 md:py-3.5",
  cell: "block px-0 py-0 md:table-cell md:px-4 md:py-3.5",
  actionsCell: "block px-0 py-0 text-right md:table-cell md:px-4 md:py-3.5",
  secondary: "mt-0.5 text-[12px] text-slate-400",
  empty:
    "flex flex-col items-center gap-2 px-5 py-16 text-center text-[13px] font-medium text-slate-400",
};

export function revisionRowClass(
  first: boolean,
  selected: boolean,
  removed: boolean,
) {
  return cn(
    "cursor-pointer flex flex-col gap-1 px-4 py-3 outline-none hover:bg-slate-50 focus-visible:bg-slate-50 md:table-row md:px-0 md:py-0",
    !first && "border-t border-slate-100",
    selected && "bg-blue-50 hover:bg-blue-50",
    removed && !selected && "bg-slate-50/60",
  );
}

export function revisionPrimaryClass(removed: boolean) {
  return cn(
    "font-semibold break-all",
    removed ? "text-slate-400 line-through" : "text-slate-900",
  );
}

export function ModelLifecycleState({ removed }: { removed: boolean }) {
  const Icon = removed ? Archive : Circle;
  return (
    <div className="flex items-start gap-1.5">
      <Icon
        aria-hidden
        className={cn(
          "mt-0.5 h-3.5 w-3.5 shrink-0",
          removed ? "text-slate-400" : "text-emerald-600",
        )}
      />
      <p className="text-[13px] font-medium text-slate-800">
        {removed ? "Removed" : "Active"}
      </p>
    </div>
  );
}
