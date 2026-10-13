"use client";

import { Button } from "@/components/ui/button";
import type { RevisionDocument } from "@/lib/documents";

export function DocumentProcessingPanel({
  row,
  busy,
  error,
  onViewPages,
  onRetry,
}: {
  row: RevisionDocument;
  busy: boolean;
  error: string | null;
  onViewPages: () => void;
  onRetry: () => void;
}) {
  const processing = row.processing;
  const pages =
    processing?.pages_total != null
      ? `${processing.pages_processed} / ${processing.pages_total}`
      : null;

  return (
    <section className="border-t border-slate-100 px-5 py-4">
      <h3 className="mb-2 text-[11px] font-bold tracking-widest text-slate-400 uppercase">
        Processing
      </h3>
      {!processing ? <p className="text-[13px] text-slate-500">Not started</p> : null}
      {processing?.status === "PENDING" ? (
        <p className="text-[13px] font-medium text-slate-700">Pending</p>
      ) : null}
      {processing?.status === "RUNNING" ? (
        <div className="text-[13px] text-slate-700">
          <p className="font-medium">In progress</p>
          {pages ? <p className="text-slate-500">{pages} pages</p> : null}
        </div>
      ) : null}
      {processing?.status === "COMPLETED" ? (
        <div className="space-y-2">
          <p className="text-[13px] font-medium text-emerald-700">Complete</p>
          {processing.pages_total != null ? (
            <p className="text-[13px] text-slate-500">
              {processing.pages_total} {processing.pages_total === 1 ? "page" : "pages"}
            </p>
          ) : null}
          <Button type="button" variant="secondary" size="sm" onClick={onViewPages}>
            View pages
          </Button>
        </div>
      ) : null}
      {processing?.status === "FAILED" ? (
        <div className="space-y-2">
          <p className="text-[13px] font-medium text-red-700">Processing failed</p>
          {processing.error_message ? (
            <p className="text-[12.5px] text-slate-500">{processing.error_message}</p>
          ) : null}
          <Button type="button" variant="secondary" size="sm" onClick={onRetry} disabled={busy}>
            Retry processing
          </Button>
        </div>
      ) : null}
      {error ? (
        <p role="alert" className="mt-2 text-[12.5px] text-red-600">
          {error}
        </p>
      ) : null}
    </section>
  );
}
