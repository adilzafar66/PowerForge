"use client";

import { Archive, Check, CircleAlert, Loader2, TriangleAlert } from "lucide-react";

import {
  deriveDocumentPresentationState,
  presentationFailureDetail,
  presentationStateLabel,
  type DocumentPresentationState,
} from "@/lib/document-presentation";
import type { RevisionDocument } from "@/lib/documents";
import { cn } from "@/lib/utils";

function progressText(row: RevisionDocument, state: DocumentPresentationState): string | null {
  if (state === "processing" && row.processing?.pages_total != null) {
    return `${row.processing.pages_processed} / ${row.processing.pages_total}`;
  }
  if (state === "classifying" && row.classification.attempt) {
    const attempt = row.classification.attempt;
    return `${attempt.pages_classified} / ${attempt.pages_total}`;
  }
  return null;
}

function StateIcon({ state }: { state: DocumentPresentationState }) {
  const className = "mt-0.5 h-3.5 w-3.5 shrink-0";
  if (state === "ready") {
    return <Check className={cn(className, "text-emerald-600")} aria-hidden />;
  }
  if (state === "processing" || state === "classifying") {
    return <Loader2 className={cn(className, "animate-spin text-slate-500")} aria-hidden />;
  }
  if (state === "needs_review") {
    return <TriangleAlert className={cn(className, "text-amber-600")} aria-hidden />;
  }
  if (state === "processing_failed" || state === "classification_failed") {
    return <CircleAlert className={cn(className, "text-red-600")} aria-hidden />;
  }
  if (state === "removed") {
    return <Archive className={cn(className, "text-slate-400")} aria-hidden />;
  }
  return null;
}

export function DocumentState({ row }: { row: RevisionDocument }) {
  const state = deriveDocumentPresentationState(row);
  const label = presentationStateLabel(state);
  const detail = presentationFailureDetail(state);
  const progress = progressText(row, state);
  const name = [detail ? `${label}, ${detail}` : label, progress].filter(Boolean).join(", ");

  return (
    <div
      role="group"
      className="flex items-start gap-1.5"
      title={detail ?? undefined}
      aria-label={name}
    >
      <StateIcon state={state} />
      <div>
        <p className="text-[13px] font-medium text-slate-800">{label}</p>
        {progress ? <p className="text-[12px] text-slate-500">{progress}</p> : null}
      </div>
    </div>
  );
}
