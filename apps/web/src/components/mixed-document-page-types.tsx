"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { keys } from "@/lib/query-keys";
import { AsyncState } from "@/components/ui/async-state";

import { docButtonClass } from "@/components/documents-ui";
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

  return (
    <div className="mt-[15px]">
      <h4 className="m-0 mb-2 text-workspace-caption font-semibold text-ink">
        Page breakdown
      </h4>
      <button
        type="button"
        className={docButtonClass("tiny")}
        onClick={() => setOpen((current) => !current)}
      >
        {open ? "Hide page classifications" : "View page classifications"}
      </button>
      {open && (
        <AsyncState
          pending={query.isPending}
          error={query.error}
          retry={query.refetch}
        />
      )}
      {open && pages ? (
        <ul className="m-0 mt-2 list-none space-y-1 p-0 text-workspace-caption">
          {pages.map((page) => (
            <li key={page.page_number}>
              <button
                type="button"
                className="cursor-pointer border-0 bg-transparent p-0 text-left text-ink hover:text-accent hover:underline"
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
