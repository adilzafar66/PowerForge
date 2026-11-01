"use client";
import { SegmentedControl } from "@/components/ui/segmented-control";
import {
  RegisterToolbar,
  RegisterTable,
  RegisterHeader,
  RegisterRow,
  RegisterCell,
  RegisterFooter,
} from "@/components/ui/register-table";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Badge } from "@/components/ui/badge";
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
      <RegisterToolbar>
        <div className="flex gap-[10px] flex-wrap items-center">
          <input
            aria-label="Search revisions"
            placeholder="Search revisions…"
            className="w-[300px] max-w-full min-h-[var(--pf-control-height-search)] bg-[var(--pf-surface-note)] border border-border rounded-[var(--pf-radius-control)] py-[10px] px-3 text-workspace-label"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <SegmentedControl
            presentation="revisions"
            label="Filter revision status"
            value={status}
            onChange={setStatus}
            options={[
              ["", "All"],
              ["ACTIVE", "Active"],
              ["DRAFT", "Draft"],
              ["SUPERSEDED", "Superseded"],
            ].map(([value, label]) => ({
              value,
              label,
              count: value
                ? revisions.filter((r) => r.status === value).length
                : revisions.length,
            }))}
          />
        </div>
        <span className="text-[11px] text-muted">
          Select a revision to open details
        </span>
      </RegisterToolbar>
      <div className="overflow-x-auto">
        <RegisterTable>
          <thead>
            <tr>
              {["Revision", "Description / lineage", "Status", "Updated"].map(
                (label) => (
                  <RegisterHeader key={label} scope="col">
                    {label}
                  </RegisterHeader>
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
                <RegisterRow
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
                  <RegisterCell>
                    <Link href={href} className="font-mono font-bold">
                      {r.identifier}
                    </Link>
                  </RegisterCell>
                  <RegisterCell>
                    <strong className="font-semibold">
                      {r.description || "—"}
                    </strong>
                    <small
                      className="block text-muted text-workspace-micro mt-[5px]"
                    >
                      {r.based_on_revision_id
                        ? `Based on ${revisions.find((item) => item.id === r.based_on_revision_id)?.identifier ?? r.based_on_identifier ?? "source revision"}`
                        : "Original revision"}
                    </small>
                  </RegisterCell>
                  <RegisterCell>
                    <Badge status={r.status} presentation="workspace" />
                  </RegisterCell>
                  <RegisterCell className="whitespace-nowrap">
                    {formatDateShort(r.updated_at)}
                  </RegisterCell>
                </RegisterRow>
              );
            })}
          </tbody>
        </RegisterTable>
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
      <RegisterFooter>
        <span>
          Showing {items.length} of {revisions.length} revisions
        </span>
        <span>Newest first</span>
      </RegisterFooter>
    </>
  );
}
