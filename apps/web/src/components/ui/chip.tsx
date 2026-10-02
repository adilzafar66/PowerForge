import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export function Chip({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "rounded-md bg-slate-100 px-2.5 py-0.5 text-[12px] font-semibold text-slate-600",
        className,
      )}
    >
      {children}
    </span>
  );
}

export function ChipList({
  items,
  empty = "—",
}: {
  items: string[];
  empty?: ReactNode;
}) {
  if (items.length === 0) {
    return <span className="text-slate-300">{empty}</span>;
  }
  return (
    <div className="flex flex-wrap gap-1.5">
      {items.map((item) => (
        <Chip key={item}>{item}</Chip>
      ))}
    </div>
  );
}
