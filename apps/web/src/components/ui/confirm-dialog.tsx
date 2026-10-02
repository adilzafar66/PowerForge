"use client";

import { Button } from "@/components/ui/button";

export function ConfirmDialog({
  title,
  message,
  confirmLabel,
  danger,
  onConfirm,
  onCancel,
}: {
  title: string;
  message: string;
  confirmLabel: string;
  danger?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/25 backdrop-blur-[2px]"
      onClick={onCancel}
      role="presentation"
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-dialog-title"
        className="w-[400px] rounded-2xl border border-slate-200 bg-white p-6 shadow-[0_24px_48px_rgba(0,0,0,0.12),0_4px_8px_rgba(0,0,0,0.06)]"
        onClick={(event) => event.stopPropagation()}
      >
        <h2 id="confirm-dialog-title" className="mb-2 text-[16px] font-semibold text-slate-900">
          {title}
        </h2>
        <p className="mb-5 text-[13.5px] leading-relaxed text-slate-500">{message}</p>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={onCancel}>
            Cancel
          </Button>
          <Button type="button" variant={danger ? "danger" : "primary"} onClick={onConfirm}>
            {confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}
