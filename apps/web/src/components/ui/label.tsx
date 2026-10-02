import * as React from "react";

import { cn } from "@/lib/utils";

function Label({ className, ...props }: React.LabelHTMLAttributes<HTMLLabelElement>) {
  return (
    <label
      className={cn(
        "text-[12.5px] font-semibold tracking-wide text-slate-500",
        className,
      )}
      {...props}
    />
  );
}

export { Label };
