"use client";

import { useEffect, useRef, type ReactNode } from "react";

import { cn } from "@/lib/utils";

/**
 * Right-side panel. Focus moves here on open and returns to the previously
 * focused element on close. Escape closes this panel unless a menu or a
 * dialog rendered above it handles the key first.
 */
export function Sheet({
  onClose,
  labelledBy,
  children,
  className,
}: {
  onClose: () => void;
  labelledBy: string;
  children: ReactNode;
  className?: string;
}) {
  const panelRef = useRef<HTMLDivElement>(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  useEffect(() => {
    const previouslyFocused =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;
    panelRef.current?.focus();

    function onKeyDown(event: KeyboardEvent) {
      if (event.key !== "Escape" || event.defaultPrevented) {
        return;
      }
      const panel = panelRef.current;
      if (!panel) {
        return;
      }
      const dialogs = document.querySelectorAll('[role="dialog"]');
      const top = dialogs.item(dialogs.length - 1);
      if (top && top !== panel && !panel.contains(top)) {
        return;
      }
      event.preventDefault();
      onCloseRef.current();
    }

    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      previouslyFocused?.focus();
    };
  }, []);

  return (
    <div className="fixed inset-0 z-40 flex justify-end">
      <div className="absolute inset-0 bg-slate-900/20" onClick={() => onCloseRef.current()} />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={labelledBy}
        tabIndex={-1}
        className={cn(
          "relative flex h-full w-full flex-col overflow-hidden border-l border-slate-200 bg-white shadow-[0_24px_48px_rgba(0,0,0,0.12)] outline-none md:max-w-[28rem]",
          className,
        )}
      >
        {children}
      </div>
    </div>
  );
}
