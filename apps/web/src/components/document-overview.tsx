"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { DocumentClassificationPanel } from "@/components/document-classification-panel";
import { DocumentMetadataPanel, DocumentTypeSection } from "@/components/document-metadata-panel";
import { DocumentProcessingPanel } from "@/components/document-processing-panel";
import { DocumentState } from "@/components/document-state";
import { MixedDocumentPageTypes } from "@/components/mixed-document-page-types";
import type { ClassificationDetail, DocumentUpdateInput, RevisionDocument } from "@/lib/documents";

export function DocumentOverview({
  row,
  projectId,
  revisionId,
  canMutate,
  detail,
  classifying,
  retrying,
  aiError,
  processingError,
  focusMetadata,
  onMetadataFocused,
  onAccept,
  onReclassify,
  onRetryClassification,
  onRetryProcessing,
  onViewPages,
  onOpenPage,
  onSave,
}: {
  row: RevisionDocument;
  projectId: string;
  revisionId: string;
  canMutate: boolean;
  detail: ClassificationDetail | null;
  classifying: boolean;
  retrying: boolean;
  aiError: string | null;
  processingError: string | null;
  focusMetadata: boolean;
  onMetadataFocused: () => void;
  onAccept: () => void;
  onReclassify: () => void;
  onRetryClassification: () => void;
  onRetryProcessing: () => void;
  onViewPages: (pageNumber?: number) => void;
  onOpenPage: (pageNumber: number) => void;
  onSave: (input: DocumentUpdateInput) => Promise<void>;
}) {
  const [typeOpen, setTypeOpen] = useState(false);

  useEffect(() => {
    setTypeOpen(false);
  }, [row.id]);

  const mixed =
    row.document_type === "MIXED_DOCUMENT" ||
    row.classification.suggestion?.predicted_type === "MIXED_DOCUMENT";

  return (
    <div className="min-h-0 flex-1 overflow-y-auto">
      <div className="px-5 pt-4">
        <DocumentState row={row} />
      </div>
      <DocumentTypeSection
        row={row}
        canMutate={canMutate}
        open={typeOpen}
        onOpen={() => setTypeOpen(true)}
        onSave={onSave}
      />
      <DocumentClassificationPanel
        row={row}
        detail={detail}
        canMutate={canMutate}
        busy={classifying}
        error={aiError}
        onAccept={onAccept}
        onChooseType={() => setTypeOpen(true)}
        onReclassify={onReclassify}
        onRetry={onRetryClassification}
      />
      {mixed ? (
        <div className="border-t border-slate-100 px-5 py-4">
          <h3 className="mb-2 text-[11px] font-bold tracking-widest text-slate-400 uppercase">
            Page breakdown
          </h3>
          <MixedDocumentPageTypes
            projectId={projectId}
            revisionId={revisionId}
            revisionDocumentId={row.id}
            onOpenPage={onOpenPage}
          />
        </div>
      ) : null}
      <DocumentProcessingPanel
        row={row}
        busy={retrying}
        error={processingError}
        onViewPages={() => onViewPages()}
        onRetry={onRetryProcessing}
      />
      <section className="border-t border-slate-100 px-5 py-4">
        <h3 className="mb-2 text-[11px] font-bold tracking-widest text-slate-400 uppercase">
          Origin
        </h3>
        <OriginLine row={row} projectId={projectId} />
      </section>
      <DocumentMetadataPanel
        row={row}
        canMutate={canMutate}
        focusField={focusMetadata}
        onFocused={onMetadataFocused}
        onSave={onSave}
      />
    </div>
  );
}

function OriginLine({ row, projectId }: { row: RevisionDocument; projectId: string }) {
  if (row.origin !== "INHERITED") {
    return <p className="text-[13px] text-slate-700">Uploaded in this revision</p>;
  }
  const identifier = row.inherited_from_revision_identifier;
  if (!identifier) {
    return <p className="text-[13px] text-slate-700">Inherited</p>;
  }
  const label = `Rev ${identifier}`;
  return (
    <p className="text-[13px] text-slate-700">
      Inherited from{" "}
      {row.inherited_from_revision_id ? (
        <Link
          href={`/projects/${projectId}/revisions/${row.inherited_from_revision_id}`}
          className="text-accent hover:underline"
        >
          {label}
        </Link>
      ) : (
        label
      )}
    </p>
  );
}
