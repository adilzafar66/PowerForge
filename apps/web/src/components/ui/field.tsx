import type { ReactNode } from "react";

import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

export function Field({
  id,
  label,
  required,
  children,
  className,
  hint,
}: {
  id?: string;
  label: string;
  required?: boolean;
  children: ReactNode;
  className?: string;
  hint?: ReactNode;
}) {
  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      <Label htmlFor={id}>
        {label}
        {required ? <span className="ml-0.5 text-red-400">*</span> : null}
      </Label>
      {children}
      {hint ? <p className="text-[12px] text-slate-400">{hint}</p> : null}
    </div>
  );
}
