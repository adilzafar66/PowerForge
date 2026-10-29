"use client";

import { useCallback, useEffect, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { EquipmentDetailDrawer } from "@/components/equipment-detail-drawer";
import { EquipmentGeneralPanel } from "@/components/equipment-general-panel";
import {
  LifecycleControl,
  LoadState,
  ModelSelect,
  ModelSheet,
  useModel,
  useModelQuery,
} from "@/components/model-shared";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  revisionTable,
  revisionRowClass,
  revisionPrimaryClass,
  ModelLifecycleState,
} from "@/components/ui/revision-table";
import { cn } from "@/lib/utils";
import { SearchField } from "@/components/ui/search-field";
import {
  equipmentLabel,
  listEquipment,
  typeLabel,
  type LifecycleFilter,
} from "@/lib/engineering-model";

export function EquipmentWorkspace({ active }: { active: boolean }) {
  const { projectId, revisionId, registry, writable, version } = useModel();
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
  const select = useCallback(
    (id: string | null) => {
      const next = new URLSearchParams(query);
      if (id) {
        next.set("workspace", "model");
        next.set("equipment", id);
        next.delete("document");
      } else next.delete("equipment");
      router.replace(`${pathname}${next.size ? `?${next}` : ""}`, {
        scroll: false,
      });
    },
    [query, router, pathname],
  );
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
  const rows = useModelQuery(load, version);
  return (
    <>
      <div className="mb-4 space-y-3">
        <div className="flex items-center justify-between gap-3">
          <h2 className="font-semibold">Equipment {rows.data?.length ?? ""}</h2>
          {writable && (
            <Button onClick={() => setAdding(true)}>Add Equipment</Button>
          )}
        </div>
        <div className="flex flex-wrap items-end gap-3">
          <SearchField
            value={searchInput}
            onChange={setSearchInput}
            placeholder="Search equipment…"
          />
          <ModelSelect
            label="Equipment type filter"
            value={type}
            onChange={setType}
          >
            <option value="">All types</option>
            {registry.equipment_types.map((t) => (
              <option key={t.key} value={t.key}>
                {t.display_name}
              </option>
            ))}
          </ModelSelect>
          <LifecycleControl value={lifecycle} onChange={setLifecycle} />
        </div>
      </div>
      <LoadState {...rows} />
      {!rows.loading && rows.data?.length === 0 && (
        <Card className={revisionTable.empty}>
          {search
            ? "No equipment matches your search."
            : type || lifecycle !== "ACTIVE"
              ? "No equipment matches these filters."
              : "No active equipment in this revision. Add equipment or view removed equipment."}
        </Card>
      )}
      {!!rows.data?.length && (
        <Card className="overflow-x-auto">
          <table className={revisionTable.table}>
            <thead className={revisionTable.head}>
              <tr className={revisionTable.headerRow}>
                <th scope="col" className={cn(revisionTable.header, "px-5")}>
                  Equipment
                </th>
                <th scope="col" className={revisionTable.header}>
                  Type
                </th>
                <th scope="col" className={revisionTable.header}>
                  State
                </th>
                <th
                  scope="col"
                  className={cn(revisionTable.header, "text-right")}
                >
                  Actions
                </th>
              </tr>
            </thead>
            <tbody
              className={cn("text-slate-700", rows.loading && "opacity-60")}
            >
              {rows.data.map((row, index) => (
                <tr
                  key={row.id}
                  tabIndex={0}
                  aria-selected={row.id === selected}
                  onClick={(event) => {
                    event.currentTarget.focus();
                    select(row.id);
                  }}
                  onKeyDown={(e) => {
                    if (
                      e.target === e.currentTarget &&
                      (e.key === "Enter" || e.key === " ")
                    ) {
                      e.preventDefault();
                      select(row.id);
                    }
                  }}
                  className={revisionRowClass(
                    index === 0,
                    row.id === selected,
                    row.lifecycle_status === "REMOVED",
                  )}
                >
                  <td className={revisionTable.primaryCell}>
                    <div
                      className={revisionPrimaryClass(
                        row.lifecycle_status === "REMOVED",
                      )}
                    >
                      {equipmentLabel(row, registry)}
                    </div>
                    <div className={revisionTable.secondary}>
                      {row.name !== row.tag ? row.name : null}
                      {row.description ? ` · ${row.description}` : ""}
                    </div>
                  </td>
                  <td className={revisionTable.cell}>
                    {typeLabel(registry, row.equipment_type)}
                  </td>
                  <td className={revisionTable.cell}>
                    <ModelLifecycleState
                      removed={row.lifecycle_status === "REMOVED"}
                    />
                  </td>
                  <td className={revisionTable.actionsCell}>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={(e) => {
                        e.stopPropagation();
                        select(row.id);
                      }}
                    >
                      Open
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
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
      {selected && active && (
        <EquipmentDetailDrawer
          key={selected}
          id={selected}
          onClose={() => select(null)}
        />
      )}
    </>
  );
}
