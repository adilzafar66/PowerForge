"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/** Documents workspace control sizes from the v1 prototype, on the production type scale. */
export const docButton = {
  base: "inline-flex h-9 cursor-pointer items-center justify-center gap-2 rounded-[var(--pf-radius-control)] border border-border bg-panel px-[13px] text-workspace-label font-semibold whitespace-nowrap text-ink transition-[background-color,border-color,transform] duration-150 select-none hover:border-[#c0ccd5] hover:bg-soft focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-[rgba(36,85,122,0.24)] active:translate-y-px disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50 [&>svg]:size-[15px] [&>svg]:shrink-0",
  primary:
    "border-accent bg-accent text-white hover:border-accent hover:bg-accent-hover",
  danger:
    "border-[var(--pf-action-destructive-border)] text-[var(--pf-action-destructive)] hover:border-[var(--pf-action-destructive-border)] hover:bg-danger-tint",
  ghost: "border-transparent bg-transparent text-accent hover:border-transparent hover:bg-selection",
  tiny: "h-[29px] px-[9px] text-workspace-caption [&>svg]:size-[14px]",
};

export function docButtonClass(
  ...variants: (keyof Omit<typeof docButton, "base"> | false | null | undefined)[]
) {
  return cn(docButton.base, ...variants.map((v) => (v ? docButton[v] : null)));
}

export function Overline({
  children,
  className,
  as: Tag = "h3",
}: {
  children: ReactNode;
  className?: string;
  as?: "h2" | "h3" | "p" | "span";
}) {
  return (
    <Tag
      className={cn(
        "m-0 mb-3 block text-workspace-overline font-bold tracking-[0.72px] text-[var(--pf-text-tertiary)] uppercase",
        className,
      )}
    >
      {children}
    </Tag>
  );
}

/** Two-column facts list from the prototype inspector. */
export function MiniGrid({
  items,
  className,
}: {
  items: [label: string, value: ReactNode][];
  className?: string;
}) {
  return (
    <dl
      className={cn(
        "m-0 grid grid-cols-[110px_1fr] gap-x-2 gap-y-[9px] text-workspace-caption",
        className,
      )}
    >
      {items.map(([label, value]) => (
        <div key={label} className="contents">
          <dt className="text-muted">{label}</dt>
          <dd className="m-0 text-ink [overflow-wrap:anywhere]">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

export function InspectorSection({
  title,
  children,
  className,
}: {
  title?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      className={cn("border-b border-border py-5 last:border-b-0", className)}
    >
      {title ? <Overline>{title}</Overline> : null}
      {children}
    </section>
  );
}

export type ChipTone = "green" | "yellow" | "red" | "gray" | "blue";

const CHIP_TONES: Record<ChipTone, string> = {
  green: "bg-positive-tint text-positive",
  yellow: "bg-warning-tint text-warning",
  red: "bg-danger-tint text-danger",
  gray: "bg-[#eef1f4] text-[#627181]",
  blue: "bg-selection text-accent",
};

export function StatusChip({
  tone,
  children,
  className,
}: {
  tone: ChipTone;
  children: ReactNode;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-[20px] px-2.5 py-[5px] text-workspace-overline font-semibold whitespace-nowrap before:size-1.5 before:rounded-full before:bg-current before:content-['']",
        CHIP_TONES[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

export function ProgressBar({
  value,
  label,
  className,
}: {
  /** 0–100 */
  value: number;
  label: string;
  className?: string;
}) {
  const clamped = Math.max(0, Math.min(100, Math.round(value)));
  return (
    <span
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={clamped}
      className={cn(
        "mt-2 block h-1 w-full max-w-[115px] overflow-hidden rounded-full bg-[var(--pf-progress-track)]",
        className,
      )}
    >
      <span
        className="block h-full rounded-[inherit] bg-accent transition-[width] duration-300"
        style={{ width: `${clamped}%` }}
      />
    </span>
  );
}

/** Prototype dialog: header with title and subtitle, scrolling body, tinted footer. */
export function DocumentsDialog({
  title,
  description,
  onClose,
  footer,
  children,
  className,
  closeLabel = "Close dialog",
}: {
  title: string;
  description?: ReactNode;
  onClose: () => void;
  footer?: ReactNode;
  children: ReactNode;
  className?: string;
  closeLabel?: string;
}) {
  return (
    <Dialog.Root
      open
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-[60] bg-[rgba(19,33,47,0.32)] animate-[workspace-appear_var(--pf-motion-overlay)_ease] motion-reduce:animate-none" />
        <Dialog.Content
          {...(description ? {} : { "aria-describedby": undefined })}
          className={cn(
            "fixed top-1/2 left-1/2 z-[70] flex max-h-[90vh] w-[calc(100%-32px)] max-w-[500px] -translate-x-1/2 -translate-y-1/2 flex-col overflow-hidden rounded-[var(--pf-radius-lg)] border border-border bg-panel shadow-[var(--pf-shadow-documents-dialog)] outline-none",
            className,
          )}
        >
          <div className="flex items-start justify-between gap-3 border-b border-border px-[22px] py-5">
            <div className="min-w-0">
              <Dialog.Title className="m-0 text-workspace-subheading leading-[1.3] font-semibold tracking-[-0.2px] text-ink">
                {title}
              </Dialog.Title>
              {description ? (
                <Dialog.Description className="m-0 mt-1 text-workspace-caption leading-[1.5] text-muted">
                  {description}
                </Dialog.Description>
              ) : null}
            </div>
            <Dialog.Close
              aria-label={closeLabel}
              className="inline-flex size-8 shrink-0 cursor-pointer items-center justify-center rounded-[var(--pf-radius-control)] border border-border text-muted hover:bg-soft focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-[rgba(36,85,122,0.24)]"
            >
              <X aria-hidden className="size-4" />
            </Dialog.Close>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto px-[22px] py-5">
            {children}
          </div>
          {footer ? (
            <div className="flex flex-wrap justify-end gap-2 border-t border-border bg-[var(--pf-documents-dialog-footer)] px-[22px] py-3.5">
              {footer}
            </div>
          ) : null}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
