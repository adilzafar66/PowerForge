"use client";
import { cn } from "@/lib/utils";

import * as Dialog from "@radix-ui/react-dialog";
import { useRef } from "react";
import { Button } from "@/components/ui/button";

export function ConfirmDialog({
  title,
  presentation = "default",
  message,
  confirmLabel,
  danger,
  onConfirm,
  onCancel,
  className = "",
}: {
  title: string;
  presentation?: "default" | "workspace";
  message: string;
  confirmLabel: string;
  danger?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
  className?: string;
}) {
  const previous = useRef<HTMLElement | null>(null);
  return (
    <Dialog.Root
      open
      onOpenChange={(open) => {
        if (!open) onCancel();
      }}
    >
      <Dialog.Portal>
        <Dialog.Overlay
          className={cn(
            "fixed inset-0 z-[60] bg-ink/25",
            presentation === "workspace" &&
              "bg-[var(--pf-overlay-workspace)] animate-[workspace-appear_var(--pf-motion-overlay)_ease]",
          )}
        />
        <Dialog.Content
          onOpenAutoFocus={() => {
            previous.current = document.activeElement as HTMLElement;
          }}
          onCloseAutoFocus={(event) => {
            event.preventDefault();
            previous.current?.focus();
          }}
          className={cn(
            "fixed top-1/2 left-1/2 z-[70] w-[calc(100%-32px)] max-w-[400px] -translate-x-1/2 -translate-y-1/2 rounded-xl border border-border bg-panel p-6 shadow-xl",
            presentation === "workspace" &&
              "max-w-[var(--pf-dialog-width)] rounded-[var(--pf-radius-dialog)] p-[25px] shadow-workspace-dialog",
            className,
          )}
        >
          <Dialog.Title
            className={cn(
              "mb-2 text-base font-semibold text-ink",
              presentation === "workspace" && "text-workspace-subheading mb-3",
            )}
          >
            {title}
          </Dialog.Title>
          <Dialog.Description
            className={cn(
              "mb-5 text-[13.5px] leading-relaxed text-muted",
              presentation === "workspace" &&
                "text-workspace-label leading-[1.7]",
            )}
          >
            {message}
          </Dialog.Description>
          <div className="flex justify-end gap-2">
            <Button
              presentation={
                presentation === "workspace" ? "workspace-dialog" : "default"
              }
              type="button"
              variant="outline"
              onClick={onCancel}
            >
              Cancel
            </Button>
            <Button
              presentation={
                presentation === "workspace" ? "workspace-dialog" : "default"
              }
              type="button"
              variant={danger ? "danger" : "primary"}
              onClick={onConfirm}
            >
              {confirmLabel}
            </Button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
