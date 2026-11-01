import { cn } from "@/lib/utils";

export type SegmentOption<T extends string> = {
  value: T;
  label: string;
  count?: number;
};

export function SegmentedControl<T extends string>({
  value,
  presentation = "default",
  options,
  onChange,
  className,
  label,
}: {
  presentation?: "default" | "projects" | "revisions";
  value: T;
  options: Array<SegmentOption<T>>;
  onChange: (value: T) => void;
  className?: string;
  /** Names the group for assistive technology and lets tests scope to it. */
  label?: string;
}) {
  return (
    <div
      role={label ? "group" : undefined}
      aria-label={label}
      className={cn(
        presentation === "default" &&
          "flex flex-wrap items-center gap-0.5 rounded-lg bg-slate-100 p-0.5",
        presentation !== "default" && "flex gap-[6px] flex-wrap",
        presentation === "projects" &&
          "p-1 bg-soft rounded-[var(--pf-radius-md)] gap-[5px]",
        className,
      )}
    >
      {options.map((option) => {
        const active = value === option.value;
        return (
          <button
            key={option.value}
            type="button"
            onClick={() => onChange(option.value)}
            aria-pressed={active}
            className={cn(
              presentation === "default" &&
                "cursor-pointer rounded-md px-3 py-1 text-[12px] font-semibold transition-colors",
              presentation === "default" &&
                (active
                  ? "bg-panel text-accent"
                  : "text-slate-500 hover:text-slate-700"),
              presentation !== "default" &&
                "py-2 px-3 border border-transparent bg-soft rounded-[var(--pf-radius-sm)] text-muted text-workspace-caption font-semibold cursor-pointer [transition:background_var(--pf-transition-fast)] hover:bg-[var(--pf-tab-hover)]",
              presentation === "projects" && "py-[7px] px-[9px]",
              presentation !== "default" &&
                active &&
                "text-accent bg-selection border-[var(--pf-tab-selected-border)] hover:bg-selection hover:text-accent",
              presentation === "projects" &&
                active &&
                "bg-panel border-transparent shadow-workspace-tab hover:bg-panel",
            )}
          >
            {option.label}
            {presentation !== "default" && " "}
            {typeof option.count === "number" ? (
              presentation === "revisions" ? (
                option.count
              ) : (
                <span
                  className={cn(
                    presentation === "default"
                      ? "ml-0.5 text-[11px]"
                      : "ml-1 opacity-70",
                    presentation === "default" &&
                      (active ? "text-slate-400" : "text-slate-400/60"),
                  )}
                >
                  {option.count}
                </span>
              )
            ) : null}
          </button>
        );
      })}
    </div>
  );
}
