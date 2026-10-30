"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { keys } from "@/lib/query-keys";
import { AsyncState } from "@/components/ui/async-state";

import { Button } from "@/components/ui/button";
import {
  getPageArtifactUrl,
  listPages,
  type DocumentPage,
  type PageArtifactInfo,
} from "@/lib/documents";

type Props = {
  projectId: string;
  revisionId: string;
  revisionDocumentId: string;
  filename: string;
  /** When set, the viewer selects this page number after the page list loads. */
  initialPageNumber?: number | null;
  onClose: () => void;
};

export function PageViewer({
  projectId,
  revisionId,
  revisionDocumentId,
  filename,
  initialPageNumber = null,
  onClose,
}: Props) {
  const docKey = keys.document(projectId, revisionId, revisionDocumentId);
  const query = useQuery({
    queryKey: [...docKey, "pages"],
    queryFn: () => listPages(projectId, revisionId, revisionDocumentId),
  });
  const pages = query.data ?? null;
  const [choice, setSelectedId] = useState<string | null>(null);
  const selectedId =
    pages?.find((page) => page.id === choice)?.id ??
    pages?.find((page) => page.page_number === initialPageNumber)?.id ??
    pages?.[0]?.id ??
    null;
  const thumbs = useQuery({
    queryKey: [...docKey, "thumbnails", pages?.map((p) => p.id)],
    enabled: !!pages,
    staleTime: 0,
    gcTime: 0,
    queryFn: async () =>
      Object.fromEntries(
        await Promise.all(
          (pages ?? [])
            .filter((page) =>
              page.artifacts.some((a) => a.artifact_type === "THUMBNAIL"),
            )
            .map(async (page) => [
              page.id,
              (
                await getPageArtifactUrl(
                  projectId,
                  revisionId,
                  revisionDocumentId,
                  page.id,
                  "THUMBNAIL",
                )
              ).url,
            ]),
        ),
      ),
  });
  const image = useQuery({
    queryKey: [...docKey, "image", selectedId],
    enabled: !!selectedId,
    staleTime: 0,
    gcTime: 0,
    queryFn: () =>
      getPageArtifactUrl(
        projectId,
        revisionId,
        revisionDocumentId,
        selectedId!,
        "ANALYSIS_IMAGE",
      ),
  });
  const analysisUrl = image.data?.url ?? null;
  const thumbnails = thumbs.data ?? {};
  const error = query.error || thumbs.error || image.error;
  const selected = pages?.find((page) => page.id === selectedId) ?? null;
  const analysis = selected ? artifactOf(selected, "ANALYSIS_IMAGE") : null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/25 p-6 backdrop-blur-[2px]"
      onClick={onClose}
      role="presentation"
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="page-viewer-title"
        className="flex max-h-[90vh] w-full max-w-4xl flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-[0_24px_48px_rgba(0,0,0,0.12)]"
        onClick={(event) => event.stopPropagation()}
      >
        <AsyncState
          pending={query.isPending}
          error={error}
          retry={() => {
            void query.refetch();
            void thumbs.refetch();
            if (selectedId) void image.refetch();
          }}
        />
        <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4">
          <h2
            id="page-viewer-title"
            className="text-[16px] font-semibold text-slate-900"
          >
            {filename}
          </h2>
          <Button type="button" variant="outline" size="sm" onClick={onClose}>
            Close
          </Button>
        </div>
        {pages === null ? null : pages.length === 0 ? (
          <p className="px-5 py-8 text-[13.5px] text-slate-400">No pages.</p>
        ) : (
          <div className="flex min-h-0 flex-1">
            <ul className="w-36 shrink-0 space-y-2 overflow-y-auto border-r border-slate-100 p-3">
              {pages.map((page) => (
                <li key={page.id}>
                  <button
                    type="button"
                    aria-pressed={page.id === selectedId}
                    onClick={() => setSelectedId(page.id)}
                    className="w-full cursor-pointer overflow-hidden rounded-lg border border-slate-200 bg-slate-50 text-left"
                  >
                    {thumbnails[page.id] ? (
                      // Signed artifact URLs are short-lived and must not be optimized or cached.
                      // eslint-disable-next-line @next/next/no-img-element
                      <img
                        src={thumbnails[page.id]}
                        alt={`Page ${page.page_number} thumbnail`}
                        className="h-24 w-full object-contain"
                      />
                    ) : (
                      <span className="block px-2 py-6 text-center text-[12px] text-slate-500">
                        Page {page.page_number}
                      </span>
                    )}
                  </button>
                </li>
              ))}
            </ul>
            {selected ? (
              <div className="min-w-0 flex-1 overflow-y-auto p-5">
                <p className="text-[13.5px] font-semibold text-slate-900">
                  Page {selected.page_number}
                </p>
                <p className="mt-1 text-[13px] text-slate-600">
                  {formatSourceSize(selected)}
                </p>
                {analysis?.width_px != null && analysis.height_px != null ? (
                  <p className="mt-1 text-[13px] text-slate-600">
                    {analysis.width_px} × {analysis.height_px} px
                  </p>
                ) : null}
                <p className="mt-1 text-[13px] text-slate-600">
                  {selected.native_text_char_count > 0
                    ? "Native text"
                    : "No native text"}
                </p>
                {analysisUrl ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={analysisUrl}
                    alt={`Page ${selected.page_number} analysis`}
                    className="mt-4 max-h-[60vh] w-full object-contain"
                  />
                ) : null}
              </div>
            ) : null}
          </div>
        )}
      </div>
    </div>
  );
}

function artifactOf(
  page: DocumentPage,
  type: PageArtifactInfo["artifact_type"],
): PageArtifactInfo | undefined {
  return page.artifacts.find((artifact) => artifact.artifact_type === type);
}

function formatSourceSize(page: DocumentPage): string {
  const unit = page.source_unit === "POINTS" ? "pt" : "px";
  return `${page.source_width} × ${page.source_height} ${unit}`;
}
