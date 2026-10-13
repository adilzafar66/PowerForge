"use client";

import { Button } from "@/components/ui/button";
import {
  classificationErrorLabel,
  confidenceBandLabel,
  documentTypeLabel,
  DOCUMENT_TYPE_LABELS,
  type ClassificationDetail,
  type DocumentType,
  type RevisionDocument,
} from "@/lib/documents";
import { canReclassifyDocument, canRetryClassification } from "@/components/document-overflow-menu";

function typeLabel(type: string): string {
  return type in DOCUMENT_TYPE_LABELS ? documentTypeLabel(type as DocumentType) : type;
}

export function DocumentClassificationPanel({
  row,
  detail,
  canMutate,
  busy,
  error,
  onAccept,
  onChooseType,
  onReclassify,
  onRetry,
}: {
  row: RevisionDocument;
  detail: ClassificationDetail | null;
  canMutate: boolean;
  busy: boolean;
  error: string | null;
  onAccept: () => void;
  onChooseType: () => void;
  onReclassify: () => void;
  onRetry: () => void;
}) {
  const suggestion = row.classification.suggestion;
  const attempt = row.classification.attempt;
  const failed = attempt?.status === "FAILED";
  const typesDiffer = suggestion != null && suggestion.predicted_type !== row.document_type;
  const editable = canMutate && row.status === "INCLUDED";
  const rationale = detail?.rationale ?? null;

  return (
    <section className="border-t border-slate-100 px-5 py-4">
      <h3 className="mb-2 text-[11px] font-bold tracking-widest text-slate-400 uppercase">
        AI Classification
      </h3>
      {suggestion ? (
        <div className="space-y-1 text-[13px] text-slate-700">
          {suggestion.accepted ? (
            <p className="font-medium text-emerald-700">Accepted AI classification</p>
          ) : null}
          <p>
            <span className="text-slate-500">
              {typesDiffer ? "AI suggestion" : "Suggested type"}
            </span>
            <span className="mt-0.5 block font-medium">
              {documentTypeLabel(suggestion.predicted_type)}
            </span>
          </p>
          <p>
            <span className="text-slate-500">Confidence</span>
            <span className="mt-0.5 block">{confidenceBandLabel(suggestion.confidence_band)}</span>
          </p>
          {detail?.confidence_score != null ? (
            <p className="text-[12.5px] text-slate-500">Score {detail.confidence_score.toFixed(2)}</p>
          ) : null}
          {rationale ? <p className="text-[13px] leading-relaxed text-slate-600">{rationale}</p> : null}
          {typesDiffer ? (
            <p className="text-[12.5px] text-slate-500">
              Confirmed: {documentTypeLabel(row.document_type)}
            </p>
          ) : null}
          {detail && detail.alternatives.length > 0 ? (
            <ul className="mt-1 text-[12.5px] text-slate-500">
              {detail.alternatives.map((alternative) => (
                <li key={`${alternative.type}-${alternative.score}`}>
                  {typeLabel(alternative.type)} · {alternative.score.toFixed(2)}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : (
        <p className="text-[13px] text-slate-500">No suggestion</p>
      )}

      {failed ? (
        <div className="mt-3 space-y-1 text-[13px]">
          {suggestion ? (
            <p className="font-medium text-slate-700">Latest attempt</p>
          ) : (
            <p className="font-medium text-red-700">Classification failed</p>
          )}
          <p className="text-red-700">Failed</p>
          <p className="text-[12.5px] text-slate-500">{classificationErrorLabel(attempt?.error_code)}</p>
          {canRetryClassification(row) ? (
            <Button type="button" variant="secondary" size="sm" onClick={onRetry} disabled={busy}>
              Retry
            </Button>
          ) : null}
        </div>
      ) : null}

      {editable && suggestion && !suggestion.accepted ? (
        <div className="mt-3 flex flex-wrap gap-2">
          <Button type="button" variant="secondary" size="sm" onClick={onAccept} disabled={busy}>
            {typesDiffer ? "Use AI suggestion" : "Accept suggestion"}
          </Button>
          {typesDiffer ? (
            <Button type="button" variant="secondary" size="sm" disabled={busy}>
              Keep current
            </Button>
          ) : (
            <Button
              type="button"
              variant="secondary"
              size="sm"
              onClick={onChooseType}
              disabled={busy}
            >
              Choose another type
            </Button>
          )}
        </div>
      ) : null}

      {canReclassifyDocument(row) ? (
        <div className="mt-3">
          <Button type="button" variant="ghost" size="sm" onClick={onReclassify} disabled={busy}>
            Reclassify
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
