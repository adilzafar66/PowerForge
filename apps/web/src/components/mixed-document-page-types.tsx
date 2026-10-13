"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { apiErrorOf } from "@/lib/api";
import {
  confidenceBandLabel,
  documentTypeLabel,
  listClassificationPages,
  type ClassificationPagePrediction,
} from "@/lib/documents";

export function MixedDocumentPageTypes({
  projectId,
  revisionId,
  revisionDocumentId,
  onOpenPage,
}: {
  projectId: string;
  revisionId: string;
  revisionDocumentId: string;
  onOpenPage: (pageNumber: number) => void;
}) {
  const [open, setOpen] = useState(false);
  const [pages, setPages] = useState<ClassificationPagePrediction[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function toggle() {
    if (!open && pages === null) {
      try {
        setPages(await listClassificationPages(projectId, revisionId, revisionDocumentId));
      } catch (err) {
        setError(apiErrorOf(err).detail);
      }
    }
    setOpen((current) => !current);
  }

  return (
    <div className="mt-3">
      <Button type="button" variant="secondary" size="sm" onClick={() => void toggle()}>
        {open ? "Hide page classifications" : "View page classifications"}
      </Button>
      {error ? (
        <p role="alert" className="mt-1 text-[12px] text-red-600">
          {error}
        </p>
      ) : null}
      {open && pages ? (
        <ul className="mt-2 space-y-1 text-[12.5px]">
          {pages.map((page) => (
            <li key={page.page_number}>
              <button
                type="button"
                className="cursor-pointer text-left text-slate-700 hover:underline"
                onClick={() => onOpenPage(page.page_number)}
              >
                {page.page_number} {documentTypeLabel(page.predicted_type)} ·{" "}
                {confidenceBandLabel(page.confidence_band)}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
