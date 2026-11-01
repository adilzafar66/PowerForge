"use client";

import { useCallback, useEffect, useState, type ReactNode } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Plus, Search } from "lucide-react";
import { EquipmentEditor } from "@/components/equipment-editor";
import { EquipmentGeneralPanel } from "@/components/equipment-general-panel";
import { EquipmentQuickDetails } from "@/components/equipment-quick-details";
import { LifecycleStatus } from "@/components/equipment-ui";
import { LoadState, ModelSheet, useModel } from "@/components/model-shared";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { cn } from "@/lib/utils";
import { useResource } from "@/lib/query-hooks";
import { keys } from "@/lib/query-keys";
import {
  equipmentLabel,
  listEquipment,
  typeLabel,
  type Equipment,
  type LifecycleFilter,
} from "@/lib/engineering-model";
import {
  clearEquipment,
  equipmentTab,
  type EquipmentTab,
} from "@/lib/workspace-navigation";

export function EquipmentWorkspace({ active }: { active: boolean }) {
  const { projectId, revisionId, registry, writable, revisionLabel } =
    useModel();
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [type, setType] = useState("");
  const [lifecycle, setLifecycle] = useState<LifecycleFilter>("ACTIVE");
  const [adding, setAdding] = useState(false);
  const params = useSearchParams();
  const query = params.toString();
  const router = useRouter();
  const pathname = usePathname();
  const selected = params.get("equipment");
  const editing = params.get("equipmentMode") === "edit" && !!selected;
  const tab = equipmentTab(params.get("equipmentTab"));
  const href = useCallback(
    (change: (next: URLSearchParams) => void) => {
      const next = new URLSearchParams(query);
      change(next);
      return `${pathname}${next.size ? `?${next}` : ""}`;
    },
    [query, pathname],
  );
  const select = useCallback(
    (id: string | null) => {
      router.replace(
        href((next) => {
          if (id) {
            next.set("workspace", "model");
            next.set("equipment", id);
            next.delete("equipmentMode");
            next.delete("equipmentTab");
            next.delete("document");
          } else clearEquipment(next);
        }),
        { scroll: false },
      );
    },
    [router, href],
  );
  const editHref = (id: string, editorTab: EquipmentTab) =>
    href((next) => {
      next.set("equipment", id);
      next.set("equipmentMode", "edit");
      next.set("equipmentTab", editorTab);
    });
  const quickHref = href((next) => {
    next.delete("equipmentMode");
    next.delete("equipmentTab");
  });
  // A dirty editor stays mounted when the URL leaves it, until the user decides.
  const target = editing ? selected : null;
  const [editor, setEditor] = useState(target);
  const [dirty, setDirty] = useState(false);
  if (editor !== target && !dirty) setEditor(target);
  useEffect(() => {
    const timer = setTimeout(() => setSearch(searchInput.trim()), 300);
    return () => clearTimeout(timer);
  }, [searchInput]);
  const load = useCallback(
    () =>
      listEquipment(projectId, revisionId, {
        search,
        equipment_type: type,
        lifecycle_status: lifecycle,
      }),
    [projectId, revisionId, search, type, lifecycle],
  );
  const rows = useResource(
    keys.equipment(projectId, revisionId, {
      search,
      equipment_type: type,
      lifecycle_status: lifecycle,
    }),
    load,
    active,
  );
  const summary = useResource(
    keys.equipment(projectId, revisionId, { lifecycle_status: "ALL" }),
    () => listEquipment(projectId, revisionId, { lifecycle_status: "ALL" }),
    active,
  );
  const counts = summary.data && {
    total: summary.data.length,
    active: summary.data.filter((e) => e.lifecycle_status === "ACTIVE").length,
    removed: summary.data.filter((e) => e.lifecycle_status === "REMOVED")
      .length,
  };
  const inLifecycle =
    counts &&
    { ALL: counts.total, ACTIVE: counts.active, REMOVED: counts.removed }[
      lifecycle
    ];
  return (
    <>
      {editor && (
        <EquipmentEditor
          key={editor}
          id={editor}
          tab={tab}
          active={active}
          leaving={active && editor !== target}
          onDirtyChange={setDirty}
          onTab={(next) =>
            router.replace(editHref(editor, next), { scroll: false })
          }
          onReturn={() => router.replace(quickHref, { scroll: false })}
          onStay={() =>
            router.replace(editHref(editor, tab), { scroll: false })
          }
          onDiscard={() => {
            setDirty(false);
            setEditor(target);
          }}
          onMissing={() => {
            setDirty(false);
            select(null);
          }}
        />
      )}
      <div hidden={!!editor && active}>
        <header className="mb-[25px] flex items-center justify-between gap-6 max-[700px]:items-start">
          <div className="min-w-0">
            <p className="m-0 mb-[7px] text-workspace-overline font-bold tracking-[1px] text-[var(--pf-text-tertiary)] uppercase">
              Engineering Model / Equipment
            </p>
            <h1 className="m-0 mb-[6px] text-workspace-title leading-[1.2] font-bold tracking-[-0.025em]">
              Equipment
            </h1>
            <p className="m-0 text-workspace-body text-muted">
              Manage electrical equipment in{" "}
              {revisionLabel ? `revision ${revisionLabel}` : "this revision"}
            </p>
          </div>
          {writable && (
            <Button
              presentation="workspace"
              variant="primary"
              className="min-h-[39px] shrink-0 px-4"
              onClick={() => setAdding(true)}
            >
              <Plus aria-hidden strokeWidth={1.7} />
              Add Equipment
            </Button>
          )}
        </header>
        <div className="mb-[26px] grid grid-cols-3 gap-[15px] max-[1230px]:gap-[10px] max-[700px]:grid-cols-2">
          <Metric value={counts?.total} label="Total equipment">
            In this revision
          </Metric>
          <Metric value={counts?.active} label="Active">
            In the working model
          </Metric>
          <Metric value={counts?.removed} label="Removed">
            Retained in history
          </Metric>
        </div>
        <div className="grid grid-cols-[minmax(0,1fr)_var(--pf-equipment-inspector)] items-start gap-5 max-[1230px]:grid-cols-[minmax(0,1fr)_var(--pf-equipment-inspector-compact)] max-[970px]:flex max-[970px]:flex-col max-[970px]:items-stretch">
          <section aria-label="Equipment register" className="min-w-0">
            <div className="mb-[15px] flex items-center gap-3 max-[1230px]:flex-wrap">
              <label className="flex h-[41px] min-w-[150px] flex-1 items-center gap-[9px] rounded-[var(--pf-radius-control)] border border-border bg-panel px-[13px] focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-[var(--pf-ring)] max-[1230px]:basis-full">
                <Search
                  aria-hidden
                  className="h-[17px] w-[17px] shrink-0 text-muted"
                  strokeWidth={1.7}
                />
                <input
                  aria-label="Search equipment"
                  value={searchInput}
                  onChange={(e) => setSearchInput(e.target.value)}
                  placeholder="Search tag, name, or description…"
                  className="w-full min-w-0 border-0 bg-transparent text-workspace-label text-ink outline-none placeholder:text-[var(--pf-text-tertiary)]"
                />
              </label>
              <FilterSelect
                label="Filter by type"
                value={type}
                onChange={setType}
                className="w-[180px]"
              >
                <option value="">All types</option>
                {registry.equipment_types.map((t) => (
                  <option key={t.key} value={t.key}>
                    {t.display_name}
                  </option>
                ))}
              </FilterSelect>
              <FilterSelect
                label="Filter by status"
                value={lifecycle}
                onChange={(value) => setLifecycle(value as LifecycleFilter)}
                className="w-[110px]"
              >
                <option value="ACTIVE">Active</option>
                <option value="ALL">All</option>
                <option value="REMOVED">Removed</option>
              </FilterSelect>
            </div>
            <LoadState {...rows} />
            <div className="overflow-hidden rounded-[11px] border border-border bg-panel">
              {rows.data && rows.data.length > 0 ? (
                <Register
                  rows={rows.data}
                  selected={selected}
                  loading={rows.refreshing}
                  onSelect={select}
                />
              ) : (
                !rows.loading &&
                rows.data && (
                  <p className="m-0 px-[22px] py-12 text-center text-workspace-body text-muted">
                    {search
                      ? "No equipment matches your search."
                      : type || lifecycle !== "ACTIVE"
                        ? "No equipment matches these filters."
                        : "No active equipment in this revision. Add equipment or view removed equipment."}
                  </p>
                )
              )}
              <p className="m-0 border-t border-border px-[21px] py-[18px] text-workspace-caption text-muted first:border-t-0">
                {rows.data
                  ? `Showing ${rows.data.length} of ${inLifecycle ?? rows.data.length} equipment`
                  : "Loading equipment…"}{" "}
                · Select an item to inspect
              </p>
            </div>
            <p className="mt-[15px] mb-0 flex items-center gap-2 text-workspace-caption text-muted before:h-[6px] before:w-[6px] before:shrink-0 before:rounded-full before:bg-accent before:content-['']">
              Quick details stay alongside the list; open the full editor to
              make changes.
            </p>
          </section>
          {selected && active && !editor && (
            <EquipmentQuickDetails
              key={selected}
              id={selected}
              onClose={() => select(null)}
              onEdit={() =>
                router.push(editHref(selected, "general"), { scroll: false })
              }
            />
          )}
        </div>
      </div>
      {adding && active && writable && (
        <ModelSheet title="Add Equipment" onClose={() => setAdding(false)}>
          <EquipmentGeneralPanel
            onSaved={(row) => {
              setAdding(false);
              select(row.id);
            }}
          />
        </ModelSheet>
      )}
    </>
  );
}

function Metric({
  value,
  label,
  children,
}: {
  value: number | undefined;
  label: string;
  children: ReactNode;
}) {
  return (
    <div
      role="group"
      aria-label={label}
      className="min-h-[91px] rounded-[11px] border border-border bg-panel px-5 py-[17px]"
    >
      <p className="m-0 text-[25px] leading-[1.12] font-bold tracking-[-0.5px]">
        {value ?? "—"}
      </p>
      <p className="m-0 mt-2 text-workspace-caption text-muted">
        <span className="font-semibold text-ink">{label}</span> · {children}
      </p>
    </div>
  );
}

function FilterSelect({
  label,
  value,
  onChange,
  className,
  children,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  className?: string;
  children: ReactNode;
}) {
  return (
    <Select
      aria-label={label}
      value={value}
      onValueChange={onChange}
      className={cn(
        "min-h-[41px] shrink-0 rounded-[var(--pf-radius-control)] border-border px-[13px] py-[9px] text-workspace-caption font-semibold text-ink hover:border-[#afc1d0] max-[1230px]:w-full",
        className,
      )}
    >
      {children}
    </Select>
  );
}

function Register({
  rows,
  selected,
  loading,
  onSelect,
}: {
  rows: Equipment[];
  selected: string | null;
  loading: boolean;
  onSelect: (id: string) => void;
}) {
  const { registry } = useModel();
  const head =
    "bg-soft px-4 py-[17px] text-left text-workspace-overline font-bold tracking-[0.8px] text-muted uppercase first:pl-[22px] max-[1230px]:px-[10px] max-[1230px]:py-3 max-[1230px]:first:pl-[22px]";
  const cell =
    "border-t border-border px-4 py-[17px] align-middle text-workspace-body text-muted max-[1230px]:px-[10px] max-[1230px]:py-3";
  return (
    <table
      className={cn(
        "w-full table-fixed border-collapse text-workspace-body",
        loading && "opacity-60",
      )}
    >
      <thead>
        <tr>
          <th scope="col" className={cn(head, "w-[41%]")}>
            Equipment
          </th>
          <th scope="col" className={cn(head, "w-[38%]")}>
            Type
          </th>
          <th scope="col" className={head}>
            Status
          </th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => {
          const isSelected = row.id === selected;
          const removed = row.lifecycle_status === "REMOVED";
          const label = equipmentLabel(row, registry);
          return (
            <tr
              key={row.id}
              tabIndex={0}
              aria-selected={isSelected}
              onClick={(event) => {
                event.currentTarget.focus();
                onSelect(row.id);
              }}
              onKeyDown={(e) => {
                if (
                  e.target === e.currentTarget &&
                  (e.key === "Enter" || e.key === " ")
                ) {
                  e.preventDefault();
                  onSelect(row.id);
                }
              }}
              className={cn(
                "cursor-pointer outline-none [transition:background-color_160ms_ease] hover:bg-[var(--pf-equipment-row-hover)] focus-visible:bg-[var(--pf-equipment-row-hover)] focus-visible:[box-shadow:inset_0_0_0_2px_var(--pf-ring)]",
                isSelected &&
                  "bg-[var(--pf-equipment-row-selected)] hover:bg-[var(--pf-equipment-row-selected)]",
              )}
            >
              <td
                className={cn(
                  cell,
                  "pl-[22px] max-[1230px]:pl-[22px]",
                  isSelected && "[box-shadow:inset_3px_0_var(--pf-action)]",
                )}
              >
                <strong
                  className={cn(
                    "block font-semibold [overflow-wrap:anywhere] text-ink",
                    removed && "text-muted line-through",
                  )}
                >
                  {label}
                </strong>
                {row.name && row.name !== label && (
                  <span className="mt-1 block text-workspace-caption text-[var(--pf-text-tertiary)] [overflow-wrap:anywhere]">
                    {row.name}
                  </span>
                )}
              </td>
              <td className={cn(cell, "[overflow-wrap:anywhere]")}>
                {typeLabel(registry, row.equipment_type)}
              </td>
              <td className={cell}>
                <LifecycleStatus status={row.lifecycle_status} />
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
