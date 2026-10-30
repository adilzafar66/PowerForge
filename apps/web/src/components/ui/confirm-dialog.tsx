"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { useRef } from "react";
import { Button } from "@/components/ui/button";

export function ConfirmDialog({
  title,
  message,
  confirmLabel,
  danger,
  onConfirm,
  onCancel,
  className = "",
}: {
  title: string;
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
          className={`fixed inset-0 z-[60] bg-ink/25 ${className.includes("ui-c-dialog") ? "ui-c-overlay" : ""}`}
        />
        <Dialog.Content
          onOpenAutoFocus={() => {
            previous.current = document.activeElement as HTMLElement;
          }}
          onCloseAutoFocus={(event) => {
            event.preventDefault();
            previous.current?.focus();
          }}
          className={`fixed top-1/2 left-1/2 z-[70] w-[calc(100%-32px)] max-w-[400px] -translate-x-1/2 -translate-y-1/2 rounded-xl border border-border bg-panel p-6 shadow-xl ${className}`}
        >
          <Dialog.Title className="mb-2 text-base font-semibold text-ink">
            {title}
          </Dialog.Title>
          <Dialog.Description className="mb-5 text-[13.5px] leading-relaxed text-muted">
            {message}
          </Dialog.Description>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={onCancel}>
              Cancel
            </Button>
            <Button
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
