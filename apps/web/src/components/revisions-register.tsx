"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { WorkspaceStatus } from "@/components/ui-c-workspace";
import { formatDateShort, type Revision } from "@/lib/projects";
import { revisionHref } from "@/lib/workspace-navigation";
export function RevisionsRegister({
  projectId,
  revisions,
}: {
  projectId: string;
  revisions: Revision[];
  filterable?: boolean;
}) {
  const router = useRouter();
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const items = [...revisions]
    .sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at))
    .filter(
      (r) =>
        (!status || r.status === status) &&
        [r.identifier, r.description, r.based_on_identifier, r.status].some(
          (value) => value?.toLowerCase().includes(search.trim().toLowerCase()),
        ),
    );
  return (
    <>
      <div className="ui-c-toolbar">
        <div className="ui-c-toolbar-controls">
          <input
            aria-label="Search revisions"
            placeholder="Search revisions…"
            className="ui-c-search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <div
            className="ui-c-tabs"
            role="group"
            aria-label="Filter revision status"
          >
            {[
              ["", "All"],
              ["ACTIVE", "Active"],
              ["DRAFT", "Draft"],
              ["SUPERSEDED", "Superseded"],
            ].map(([value, label]) => (
              <button
                key={value}
                type="button"
                aria-pressed={status === value}
                onClick={() => setStatus(value)}
              >
                {label}{" "}
                {value
                  ? revisions.filter((r) => r.status === value).length
                  : revisions.length}
              </button>
            ))}
          </div>
        </div>
        <span className="text-[11px] text-muted">
          Select a revision to open details
        </span>
      </div>
      <div className="ui-c-table-scroll">
        <table className="ui-c-table">
          <thead>
            <tr>
              {["Revision", "Description / lineage", "Status", "Updated"].map(
                (label) => (
                  <th key={label} scope="col">
                    {label}
                  </th>
                ),
              )}
            </tr>
          </thead>
          <tbody>
            {items.map((r) => {
              const href = revisionHref(
                projectId,
                r.id,
                undefined,
                "",
                "overview",
              );
              return (
                <tr
                  key={r.id}
                  tabIndex={0}
                  aria-label={`Open revision ${r.identifier}`}
                  onKeyDown={(e) => {
                    if (
                      e.target === e.currentTarget &&
                      (e.key === "Enter" || e.key === " ")
                    ) {
                      e.preventDefault();
                      router.push(href);
                    }
                  }}
                  onClick={(e) => {
                    if (!(e.target as HTMLElement).closest("a"))
                      router.push(href);
                  }}
                >
                  <td>
                    <Link href={href} className="font-mono font-bold">
                      {r.identifier}
                    </Link>
                  </td>
                  <td>
                    <strong>{r.description || "—"}</strong>
                    <small>
                      {r.based_on_revision_id
                        ? `Based on ${revisions.find((item) => item.id === r.based_on_revision_id)?.identifier ?? r.based_on_identifier ?? "source revision"}`
                        : "Original revision"}
                    </small>
                  </td>
                  <td>
                    <WorkspaceStatus status={r.status} />
                  </td>
                  <td className="whitespace-nowrap">
                    {formatDateShort(r.updated_at)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {items.length === 0 && (
        <div className="p-10 text-center text-muted">
          No revisions match your filters.{" "}
          {(search || status) && (
            <button
              className="ml-2 text-accent underline"
              onClick={() => {
                setSearch("");
                setStatus("");
              }}
            >
              Clear filters
            </button>
          )}
        </div>
      )}
      <div className="ui-c-table-footer">
        <span>
          Showing {items.length} of {revisions.length} revisions
        </span>
        <span>Newest first</span>
      </div>
    </>
  );
}
