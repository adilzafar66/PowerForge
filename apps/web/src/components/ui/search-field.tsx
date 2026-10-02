import { Search } from "lucide-react";
import type { KeyboardEventHandler } from "react";

import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

export function SearchField({
  value,
  onChange,
  placeholder = "Search…",
  className,
  onKeyDown,
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  className?: string;
  onKeyDown?: KeyboardEventHandler<HTMLInputElement>;
}) {
  return (
    <div className={cn("relative", className)}>
      <span className="pointer-events-none absolute top-1/2 left-2.5 -translate-y-1/2 text-slate-400">
        <Search className="h-3.5 w-3.5" strokeWidth={1.6} />
      </span>
      <Input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={onKeyDown}
        placeholder={placeholder}
        className="w-72 py-2 pr-3 pl-8 text-[13px]"
        aria-label="Search"
      />
    </div>
  );
}
