import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export function Mono({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return <span className={cn("font-mono text-[12px]", className)}>{children}</span>;
}
