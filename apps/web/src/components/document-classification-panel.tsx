"use client";

import { Check, RefreshCw } from "lucide-react";
import { useState, type ReactNode } from "react";

import { CellStateView } from "@/components/document-list";
import {
  docButtonClass,
  InspectorSection,
  MiniGrid,
} from "@/components/documents-ui";
import { classificationCell } from "@/lib/document-presentation";
import {
  classificationErrorLabel,
  confidenceBandLabel,
  documentTypeLabel,
  DOCUMENT_TYPE_LABELS,
  type ClassificationDetail,
  type DocumentType,
  type RevisionDocument,
} from "@/lib/documents";
import {
  canReclassifyDocument,
  canRetryClassification,
} from "@/components/document-overflow-menu";

function typeLabel(type: string): string {
  return type in DOCUMENT_TYPE_LABELS
    ? documentTypeLabel(type as DocumentType)
    : type;
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
  children,
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
  /** Page breakdown for mixed documents. */
  children?: ReactNode;
}) {
  const [kept, setKept] = useState<string | null>(null);
  const suggestion = row.classification.suggestion;
  const attempt = row.classification.attempt;
  const failed = attempt?.status === "FAILED";
  const typesDiffer =
    suggestion != null && suggestion.predicted_type !== row.document_type;
  const editable = canMutate && row.status === "INCLUDED";
  const rationale = detail?.rationale ?? null;
  const keptCurrent = suggestion != null && kept === suggestion.prediction_id;

  return (
    <InspectorSection title="AI classification">
      <CellStateView state={classificationCell(row)} />
      {suggestion?.accepted ? (
        <p className="sr-only">Accepted AI classification</p>
      ) : null}
      {suggestion ? (
        <>
          <MiniGrid
            className="mt-[13px]"
            items={[
              [
                typesDiffer ? "AI suggestion" : "Suggested type",
                documentTypeLabel(suggestion.predicted_type),
              ],
              [
                "Confidence",
                <>
                  {confidenceBandLabel(suggestion.confidence_band)}
                  {detail?.confidence_score != null ? (
                    <span className="block text-muted">
                      Score {detail.confidence_score.toFixed(2)}
                    </span>
                  ) : null}
                </>,
              ],
              ["Accepted", suggestion.accepted ? "Yes" : "No"],
              ...(typesDiffer
                ? ([["Confirmed", documentTypeLabel(row.document_type)]] as [
                    string,
                    ReactNode,
                  ][])
                : []),
            ]}
          />
          {rationale ? (
            <p className="m-0 mt-3 text-workspace-caption leading-[1.55] text-muted">
              {rationale}
            </p>
          ) : null}
          {detail && detail.alternatives.length > 0 ? (
            <ul className="m-0 mt-2 list-none p-0 text-workspace-caption text-muted">
              {detail.alternatives.map((alternative) => (
                <li key={`${alternative.type}-${alternative.score}`}>
                  {typeLabel(alternative.type)} · {alternative.score.toFixed(2)}
                </li>
              ))}
            </ul>
          ) : null}
        </>
      ) : !attempt || attempt.status === "COMPLETED" ? (
        <p className="m-0 mt-2 text-workspace-caption text-muted">No suggestion</p>
      ) : null}

      {failed ? (
        <div className="mt-3 text-workspace-caption">
          <p className="m-0 font-semibold text-ink">
            {suggestion ? "Latest attempt failed" : "Classification failed"}
          </p>
          <p className="m-0 mt-0.5 text-muted">
            {classificationErrorLabel(attempt?.error_code)}
          </p>
        </div>
      ) : null}

      {children}

      {keptCurrent ? (
        <p role="status" className="m-0 mt-3 text-workspace-caption text-muted">
          Confirmed type kept. The suggestion stays unaccepted.
        </p>
      ) : null}

      <div className="flex flex-wrap gap-2 empty:hidden [&:not(:empty)]:mt-[15px]">
        {editable && suggestion && !suggestion.accepted && !keptCurrent ? (
          <>
            <button
              type="button"
              className={docButtonClass("tiny", "primary")}
              onClick={onAccept}
              disabled={busy}
            >
              <Check aria-hidden strokeWidth={2} />
              {typesDiffer ? "Use AI suggestion" : "Accept suggestion"}
            </button>
            {typesDiffer ? (
              <button
                type="button"
                className={docButtonClass("tiny")}
                disabled={busy}
                onClick={() => setKept(suggestion.prediction_id)}
              >
                Keep current
              </button>
            ) : (
              <button
                type="button"
                className={docButtonClass("tiny")}
                onClick={onChooseType}
                disabled={busy}
              >
                Choose another type
              </button>
            )}
          </>
        ) : null}
        {failed && canRetryClassification(row) ? (
          <button
            type="button"
            className={docButtonClass("tiny")}
            onClick={onRetry}
            disabled={busy}
          >
            <RefreshCw aria-hidden strokeWidth={1.8} />
            Retry
          </button>
        ) : null}
        {canReclassifyDocument(row) ? (
          <button
            type="button"
            className={docButtonClass("tiny", "ghost")}
            onClick={onReclassify}
            disabled={busy}
          >
            Reclassify
          </button>
        ) : null}
      </div>

      {error ? (
        <p role="alert" className="m-0 mt-2 text-workspace-caption text-danger">
          {error}
        </p>
      ) : null}
    </InspectorSection>
  );
}
