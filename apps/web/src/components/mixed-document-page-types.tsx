"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { keys } from "@/lib/query-keys";
import { AsyncState } from "@/components/ui/async-state";

import { Button } from "@/components/ui/button";
import {
  confidenceBandLabel,
  documentTypeLabel,
  listClassificationPages,
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
  const query = useQuery({
    queryKey: [
      ...keys.document(projectId, revisionId, revisionDocumentId),
      "classification-pages",
    ],
    queryFn: () =>
      listClassificationPages(projectId, revisionId, revisionDocumentId),
    enabled: open,
  });
  const pages = query.data;

  async function toggle() {
    setOpen((current) => !current);
  }

  return (
    <div className="mt-3">
      <Button
        type="button"
        variant="secondary"
        size="sm"
        onClick={() => void toggle()}
      >
        {open ? "Hide page classifications" : "View page classifications"}
      </Button>
      {open && (
        <AsyncState
          pending={query.isPending}
          error={query.error}
          retry={query.refetch}
        />
      )}
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
