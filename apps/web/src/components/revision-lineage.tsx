import Link from "next/link";

import { cn } from "@/lib/utils";

/** "Based on Revision X" for a revision that records a base; renders nothing otherwise. */
export function RevisionLineage({
  basedOnIdentifier,
  href,
  className,
}: {
  basedOnIdentifier: string | null;
  href?: string;
  className?: string;
}) {
  if (!basedOnIdentifier) {
    return null;
  }
  const label = `Revision ${basedOnIdentifier}`;
  return (
    <span className={cn("text-[12px] text-slate-400", className)}>
      Based on{" "}
      {href ? (
        <Link href={href} className="font-medium text-slate-500 hover:text-accent">
          {label}
        </Link>
      ) : (
        <span className="font-medium text-slate-500">{label}</span>
      )}
    </span>
  );
}
