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
import { Chip } from "@/components/ui/chip";
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
        <Card className="p-6 text-sm text-slate-500">
          {search
            ? "No equipment matches your search."
            : type || lifecycle !== "ACTIVE"
              ? "No equipment matches these filters."
              : "No active equipment in this revision. Add equipment or view removed equipment."}
        </Card>
      )}
      {!!rows.data?.length && (
        <Card className="overflow-hidden">
          <table className="block w-full text-left text-sm md:table">
            <thead className="hidden bg-slate-50 text-xs text-slate-500 md:table-header-group">
              <tr>
                <th className="p-4">Equipment</th>
                <th className="p-4">Type</th>
                <th className="p-4">State</th>
                <th className="p-4">Actions</th>
              </tr>
            </thead>
            <tbody className="block md:table-row-group">
              {rows.data.map((row) => (
                <tr
                  key={row.id}
                  tabIndex={0}
                  onClick={() => select(row.id)}
                  onKeyDown={(e) => {
                    if (
                      e.target === e.currentTarget &&
                      (e.key === "Enter" || e.key === " ")
                    ) {
                      e.preventDefault();
                      select(row.id);
                    }
                  }}
                  className={`block cursor-pointer border-t border-slate-100 hover:bg-slate-50 focus-visible:outline-blue-500 md:table-row ${row.lifecycle_status === "REMOVED" ? "text-slate-400" : "text-slate-700"}`}
                >
                  <td className="block p-4 md:table-cell">
                    <div className="font-semibold">
                      {equipmentLabel(row, registry)}
                    </div>
                    <div className="text-xs">
                      {row.name !== row.tag ? row.name : null}
                      {row.description ? ` · ${row.description}` : ""}
                    </div>
                  </td>
                  <td className="block px-4 pb-2 md:table-cell md:p-4">
                    {typeLabel(registry, row.equipment_type)}
                  </td>
                  <td className="block px-4 pb-2 md:table-cell md:p-4">
                    <Chip>
                      {row.lifecycle_status === "ACTIVE" ? "Active" : "Removed"}
                    </Chip>
                  </td>
                  <td className="block px-4 pb-4 md:table-cell md:p-4">
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
