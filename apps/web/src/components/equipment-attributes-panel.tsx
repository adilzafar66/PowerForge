"use client";
import { useId, useState } from "react";
import {
  GroupTitle,
  INFORMATION_STATE_LABELS,
  RequirementPill,
} from "@/components/equipment-ui";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import type {
  AttributeDefinition,
  EquipmentAttribute,
  InformationState,
  ManualState,
} from "@/lib/engineering-model";
import type { AttributeDraft } from "@/lib/equipment-draft";
import { cn } from "@/lib/utils";

const MANUAL_STATES: ManualState[] = [
  "PRESENT",
  "NOT_POPULATED",
  "MISSING",
  "NOT_APPLICABLE",
];
type Show = "all" | "required" | "critical" | "not_populated";

const grid =
  "grid grid-cols-[minmax(0,1.3fr)_minmax(0,1.2fr)_70px_152px] items-center gap-[11px] px-[15px] py-[13px] max-[700px]:grid-cols-[minmax(0,1fr)_70px]";
const control =
  "min-h-[37px] w-full min-w-0 rounded-[7px] border-border bg-panel px-[9px] py-[7px] text-workspace-caption text-ink disabled:bg-[var(--pf-control-disabled)] disabled:text-[#8c9aa8] disabled:opacity-100";

export function EquipmentAttributesPanel({
  definitions,
  attributes,
  draft,
  onChange,
  editable,
}: {
  definitions: AttributeDefinition[];
  attributes: EquipmentAttribute[];
  draft: Record<string, AttributeDraft>;
  onChange: (key: string, value: AttributeDraft) => void;
  editable: boolean;
}) {
  const id = useId();
  const [search, setSearch] = useState("");
  const [show, setShow] = useState<Show>("all");
  const critical = definitions.filter((d) => d.critical).length;
  const term = search.trim().toLowerCase();
  const rows = definitions.flatMap((definition) => {
    const row = attributes.find((a) => a.attribute_key === definition.key);
    const value = draft[definition.key];
    if (!row || !value) return [];
    if (
      term &&
      !definition.display_name.toLowerCase().includes(term) &&
      !definition.key.toLowerCase().includes(term)
    )
      return [];
    if (show === "required" && !definition.required) return [];
    if (show === "critical" && !definition.critical) return [];
    if (show === "not_populated" && row.information_state !== "NOT_POPULATED")
      return [];
    return [{ definition, row, value }];
  });
  return (
    <>
      <GroupTitle title="Electrical characteristics">
        {critical
          ? `${critical} critical ${critical === 1 ? "attribute" : "attributes"}`
          : `${definitions.length} ${definitions.length === 1 ? "attribute" : "attributes"}`}{" "}
        · Registry-driven
      </GroupTitle>
      {definitions.length === 0 ? (
        <p className="m-0 rounded-[var(--pf-radius-control)] border border-border bg-[var(--pf-surface-note)] px-[15px] py-[13px] text-workspace-caption text-muted">
          The registry defines no attributes for this equipment type.
        </p>
      ) : (
        <div>
          <div
            aria-hidden
            className={cn(
              grid,
              "rounded-t-[var(--pf-radius-control)] border border-border bg-soft text-workspace-overline font-bold tracking-[0.8px] text-muted uppercase max-[700px]:hidden",
            )}
          >
            <span>Attribute</span>
            <span>Value</span>
            <span>Unit</span>
            <span>Information state</span>
          </div>
          {rows.map(({ definition, row, value }) => (
            <AttributeRow
              key={definition.key}
              definition={definition}
              initial={row}
              draft={value}
              setDraft={(next) => onChange(definition.key, next)}
              editable={editable}
            />
          ))}
          {rows.length === 0 && (
            <p className="m-0 rounded-b-[var(--pf-radius-control)] border border-t-0 border-border px-[15px] py-[13px] text-workspace-caption text-muted max-[700px]:rounded-[var(--pf-radius-control)] max-[700px]:border-t">
              No attributes match these filters.
            </p>
          )}
        </div>
      )}
      <p className="mt-[14px] mb-0 rounded-[var(--pf-radius-control)] border border-border bg-[var(--pf-surface-note)] px-[15px] py-[13px] text-workspace-caption leading-[var(--pf-leading-hint)] text-muted">
        <strong className="font-semibold text-ink">Provenance</strong> is shown
        beneath each attribute as origin · verification. Numeric values are kept
        exactly as entered; changing the unit changes how your input is
        interpreted, and conversion occurs on save.
      </p>
      <hr className="my-[23px] border-0 border-t border-border" />
      <GroupTitle title="Attribute tools" />
      <div className="grid grid-cols-2 gap-[18px] max-[700px]:grid-cols-1">
        <Field
          id={`${id}-search`}
          presentation="workspace"
          label="Find an attribute"
        >
          <Input
            id={`${id}-search`}
            presentation="workspace"
            value={search}
            placeholder="Search attribute name…"
            onChange={(e) => setSearch(e.target.value)}
          />
        </Field>
        <Field id={`${id}-show`} presentation="workspace" label="Show">
          <Select
            id={`${id}-show`}
            presentation="workspace"
            value={show}
            onValueChange={(next) => setShow(next as Show)}
          >
            <option value="all">All attributes</option>
            <option value="required">Required</option>
            <option value="critical">Critical</option>
            <option value="not_populated">Not populated</option>
          </Select>
        </Field>
      </div>
    </>
  );
}

function AttributeRow({
  definition,
  initial,
  draft,
  setDraft,
  editable,
}: {
  definition: AttributeDefinition;
  initial: EquipmentAttribute;
  draft: AttributeDraft;
  setDraft: (draft: AttributeDraft) => void;
  editable: boolean;
}) {
  const present = draft.state === "PRESENT";
  const manual = MANUAL_STATES.includes(draft.state as ManualState);
  const numeric =
    definition.value_type === "NUMBER" || definition.value_type === "INTEGER";
  const choice =
    definition.value_type === "ENUM" || definition.value_type === "BOOLEAN";
  const invalid =
    present &&
    ((definition.value_type === "BOOLEAN" &&
      !["true", "false"].includes(draft.value)) ||
      ((numeric || definition.value_type === "ENUM") && !draft.value.trim()));
  const units = numeric ? definition.supported_input_units : [];
  return (
    <section
      role="group"
      aria-label={definition.display_name}
      className="border-x border-b border-border last-of-type:rounded-b-[var(--pf-radius-control)] max-[700px]:first-of-type:rounded-t-[var(--pf-radius-control)] max-[700px]:first-of-type:border-t"
    >
      <div className={grid}>
        <div className="min-w-0 max-[700px]:col-span-2">
          <h3 className="m-0 text-workspace-caption font-semibold text-ink">
            <span className="[overflow-wrap:anywhere]">
              {definition.display_name}
            </span>
            {definition.required && (
              <RequirementPill tone="required">Required</RequirementPill>
            )}
            {definition.critical && <RequirementPill>Critical</RequirementPill>}
            {(definition.requirement_group ||
              definition.requirement_condition) && (
              <RequirementPill>Conditional</RequirementPill>
            )}
          </h3>
          {definition.notes && (
            <p className="mt-[5px] mb-0 text-[11.5px] leading-[1.4] text-muted">
              {definition.notes}
            </p>
          )}
          {definition.requirement_condition && (
            <p className="mt-[5px] mb-0 text-[11.5px] leading-[1.4] text-muted">
              {definition.requirement_condition}
            </p>
          )}
          <p className="mt-[5px] mb-0 text-[11.5px] leading-[1.4] text-[var(--pf-text-tertiary)]">
            {initial.origin ?? "No origin"} · {initial.verification_state}
            {initial.confidence != null
              ? ` · Confidence ${initial.confidence}`
              : ""}
          </p>
        </div>
        <div className="min-w-0">
          {present && choice ? (
            <Select
              aria-label="Value"
              aria-invalid={invalid || undefined}
              className={control}
              value={draft.value}
              disabled={!editable}
              onValueChange={(value) => setDraft({ ...draft, value })}
            >
              <option value="" disabled>
                Select value
              </option>
              {definition.value_type === "ENUM" ? (
                definition.allowed_values.map((v) => (
                  <option key={v} value={v}>
                    {v}
                  </option>
                ))
              ) : (
                <>
                  <option value="true">True</option>
                  <option value="false">False</option>
                </>
              )}
            </Select>
          ) : (
            <Input
              aria-label="Value"
              aria-invalid={invalid || undefined}
              className={control}
              value={present ? draft.value : ""}
              placeholder={draft.state === "CONFLICTING" ? "Conflicting" : "—"}
              disabled={!editable || !present}
              inputMode={
                numeric
                  ? definition.value_type === "INTEGER"
                    ? "numeric"
                    : "decimal"
                  : "text"
              }
              onChange={(e) => setDraft({ ...draft, value: e.target.value })}
            />
          )}
        </div>
        <div className="min-w-0">
          {present && units.length > 0 ? (
            <Select
              aria-label="Input unit"
              className={cn(control, "gap-1 px-2")}
              value={draft.unit}
              disabled={!editable}
              onValueChange={(unit) => setDraft({ ...draft, unit })}
            >
              {units.map((unit) => (
                <option key={unit} value={unit}>
                  {unit}
                </option>
              ))}
            </Select>
          ) : (
            <span
              className={cn(
                control,
                "flex items-center border bg-[var(--pf-control-disabled)] text-[#8c9aa8]",
              )}
            >
              {present && definition.canonical_unit
                ? definition.canonical_unit
                : "—"}
            </span>
          )}
        </div>
        <div className="min-w-0 max-[700px]:col-span-2">
          <Select
            aria-label="Information state"
            className={control}
            value={draft.state}
            disabled={!editable}
            onValueChange={(state) =>
              setDraft({ ...draft, state: state as InformationState })
            }
          >
            {!manual && (
              <option value={draft.state} disabled>
                {INFORMATION_STATE_LABELS[draft.state]}
              </option>
            )}
            {MANUAL_STATES.map((state) => (
              <option key={state} value={state}>
                {INFORMATION_STATE_LABELS[state]}
              </option>
            ))}
          </Select>
        </div>
      </div>
    </section>
  );
}
