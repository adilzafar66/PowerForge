"use client";

import {
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { MoreVertical } from "lucide-react";

import { cn } from "@/lib/utils";

export type DropdownMenuItem = {
  id: string;
  label: ReactNode;
  onSelect: () => void;
  disabled?: boolean;
  destructive?: boolean;
  separatorBefore?: boolean;
};

export function DropdownMenu({
  items,
  label = "Open menu",
  align = "right",
  disabled = false,
  className,
  triggerClassName,
}: {
  items: DropdownMenuItem[];
  label?: string;
  align?: "left" | "right";
  disabled?: boolean;
  className?: string;
  triggerClassName?: string;
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const menuId = useId();
  const visibleItems = items.filter(Boolean);

  const close = useCallback(() => setOpen(false), []);

  useEffect(() => {
    if (!open) {
      return;
    }

    function onPointerDown(event: MouseEvent) {
      if (!rootRef.current?.contains(event.target as Node)) {
        close();
      }
    }

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        close();
      }
    }

    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open, close]);

  if (visibleItems.length === 0) {
    return null;
  }

  return (
    <div ref={rootRef} className={cn("relative inline-flex", className)}>
      <button
        type="button"
        aria-label={label}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={menuId}
        disabled={disabled}
        onClick={() => setOpen((value) => !value)}
        className={cn(
          "inline-flex h-8 w-8 cursor-pointer items-center justify-center rounded-lg text-slate-400 transition-colors hover:text-slate-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-1 disabled:cursor-not-allowed disabled:opacity-40",
          triggerClassName,
        )}
      >
        <MoreVertical className="h-5 w-5" strokeWidth={2} />
      </button>

      {open ? (
        <div
          id={menuId}
          role="menu"
          aria-label={label}
          className={cn(
            "absolute top-full z-50 mt-1.5 min-w-[180px] overflow-hidden rounded-xl border border-slate-200 bg-white py-1 shadow-[0_12px_28px_rgba(0,0,0,0.12),0_2px_6px_rgba(0,0,0,0.06)]",
            align === "right" ? "right-0" : "left-0",
          )}
        >
          {visibleItems.map((item) => (
            <div key={item.id}>
              {item.separatorBefore ? (
                <div className="my-1 border-t border-slate-100" role="separator" />
              ) : null}
              <button
                type="button"
                role="menuitem"
                disabled={item.disabled}
                onClick={() => {
                  if (item.disabled) {
                    return;
                  }
                  item.onSelect();
                  close();
                }}
                className={cn(
                  "flex w-full cursor-pointer items-center px-3 py-2 text-left text-[13px] font-medium transition-colors focus-visible:bg-slate-50 focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-40",
                  item.destructive
                    ? "text-red-600 hover:bg-red-50"
                    : "text-slate-700 hover:bg-slate-50",
                )}
              >
                {item.label}
              </button>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}
