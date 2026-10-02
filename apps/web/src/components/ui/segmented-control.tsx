import { cn } from "@/lib/utils";

export type SegmentOption<T extends string> = {
  value: T;
  label: string;
  count?: number;
};

export function SegmentedControl<T extends string>({
  value,
  options,
  onChange,
  className,
}: {
  value: T;
  options: Array<SegmentOption<T>>;
  onChange: (value: T) => void;
  className?: string;
}) {
  return (
    <div className={cn("flex items-center gap-0.5 rounded-lg bg-slate-100 p-0.5", className)}>
      {options.map((option) => {
        const active = value === option.value;
        return (
          <button
            key={option.value}
            type="button"
            onClick={() => onChange(option.value)}
            className={cn(
              "cursor-pointer rounded-md px-3 py-1 text-[12px] font-semibold transition-all",
              active
                ? "bg-white text-slate-800 shadow-[0_1px_2px_rgba(0,0,0,0.08)]"
                : "text-slate-500 hover:text-slate-700",
            )}
          >
            {option.label}
            {typeof option.count === "number" ? (
              <span
                className={cn(
                  "ml-0.5 text-[11px]",
                  active ? "text-slate-400" : "text-slate-400/60",
                )}
              >
                {option.count}
              </span>
            ) : null}
          </button>
        );
      })}
    </div>
  );
}
