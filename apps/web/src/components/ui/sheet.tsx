"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { useRef, type ReactNode } from "react";
import { cn } from "@/lib/utils";

/** Controlled modal: the caller's dirty/pending guard decides whether it closes. */
export function Sheet({
  onClose,
  presentation = "default",
  labelledBy,
  children,
  className,
  modal = true,
  overlayClassName,
  autoFocusFirst = false,
}: {
  onClose: () => void;
  presentation?: "default" | "workspace-project" | "workspace-revision";
  labelledBy: string;
  children: ReactNode;
  className?: string;
  modal?: boolean;
  overlayClassName?: string;
  autoFocusFirst?: boolean;
}) {
  const previous = useRef<HTMLElement | null>(null);
  return (
    <Dialog.Root
      open
      modal={modal}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <Dialog.Portal>
        {modal && (
          <Dialog.Overlay
            className={cn(
              "fixed inset-0 z-40 bg-ink/20",
              presentation !== "default" &&
                "bg-[var(--pf-overlay-workspace)] animate-[workspace-appear_var(--pf-motion-overlay)_ease]",
              overlayClassName,
            )}
          />
        )}
        <Dialog.Content
          aria-labelledby={labelledBy}
          aria-describedby={undefined}
          onInteractOutside={(event) => {
            if (!modal) event.preventDefault();
          }}
          onOpenAutoFocus={(event) => {
            previous.current = document.activeElement as HTMLElement;
            event.preventDefault();
            const panel = event.currentTarget as HTMLElement;
            const first = autoFocusFirst
              ? panel.querySelector<HTMLElement>(
                  "input:not(:disabled), textarea:not(:disabled)",
                )
              : null;
            (first ?? panel).focus();
          }}
          onCloseAutoFocus={(event) => {
            event.preventDefault();
            previous.current?.focus();
          }}
          className={cn(
            "fixed inset-y-0 right-0 z-50 flex w-full flex-col overflow-hidden border-l border-border bg-panel shadow-xl outline-none md:max-w-[28rem]",
            presentation !== "default" &&
              "leading-[normal] w-[min(var(--pf-drawer-width),_100%)] max-w-none shadow-workspace-drawer animate-[workspace-slide_var(--pf-motion-drawer)_var(--pf-ease-drawer)] motion-reduce:animate-none md:max-w-none",
            presentation === "workspace-project" &&
              "w-[min(var(--pf-drawer-project-width),_94vw)]",
            className,
          )}
        >
          <Dialog.Title className="sr-only">Details</Dialog.Title>
          {children}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
