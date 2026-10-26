"use client";

import { useCallback, useId, useState, type FormEvent } from "react";
import {
  LoadState,
  ModelNotice,
  ModelSelect,
  useModel,
  useModelQuery,
} from "@/components/model-shared";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Chip } from "@/components/ui/chip";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { apiErrorOf } from "@/lib/api";
import {
  listAttributes,
  setAttribute,
  type AttributeDefinition,
  type Equipment,
  type EquipmentAttribute,
  type InformationState,
  type ManualState,
} from "@/lib/engineering-model";

const states: { value: ManualState; label: string }[] = [
  { value: "PRESENT", label: "Present" },
  { value: "UNKNOWN", label: "Unknown" },
  { value: "MISSING", label: "Missing" },
  { value: "NOT_APPLICABLE", label: "Not applicable" },
];
function draftOf(row: EquipmentAttribute) {
  const value =
    row.numeric_value ??
    row.integer_value ??
    row.text_value ??
    row.boolean_value;
  return {
    state: row.information_state,
    value: value == null ? "" : String(value),
    unit: row.unit ?? "",
  };
}
export function EquipmentAttributesPanel({ row }: { row: Equipment }) {
  const { projectId, revisionId, registry, version } = useModel();
  const load = useCallback(
    () => listAttributes(projectId, revisionId, row.id),
    [projectId, revisionId, row.id],
  );
  const query = useModelQuery(load, `${row.equipment_type}:${version}`);
  const definition = registry.equipment_types.find(
    (t) => t.key === row.equipment_type,
  );
  return (
    <div className="space-y-4">
      <LoadState {...query} />
      {!query.loading &&
        query.data &&
        definition?.attributes.map((attr) => {
          const persisted = query.data!.find(
            (a) => a.attribute_key === attr.key,
          );
          return persisted ? (
            <AttributeEditor
              key={`${persisted.id}:${persisted.updated_at}`}
              definition={attr}
              initial={persisted}
              active={row.lifecycle_status === "ACTIVE"}
            />
          ) : (
            <ModelNotice key={attr.key}>
              {attr.display_name} is unavailable. Reload equipment before
              editing.
            </ModelNotice>
          );
        })}
    </div>
  );
}
export function AttributeEditor({
  definition,
  initial,
  active,
}: {
  definition: AttributeDefinition;
  initial: EquipmentAttribute;
  active: boolean;
}) {
  const { projectId, revisionId, writable, failed } = useModel();
  const [row, setRow] = useState(initial);
  const [draft, setDraft] = useState(draftOf(initial));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const id = useId();
  const editable = writable && active;
  const original = draftOf(row);
  const present = draft.state === "PRESENT";
  const manual = states.some((s) => s.value === draft.state);
  const dirty =
    draft.state !== original.state ||
    (present &&
      (draft.value !== original.value || draft.unit !== original.unit));
  const numeric =
    definition.value_type === "NUMBER" || definition.value_type === "INTEGER";
  const needsBooleanChoice =
    present &&
    definition.value_type === "BOOLEAN" &&
    draft.value !== "true" &&
    draft.value !== "false";
  async function save(event: FormEvent) {
    event.preventDefault();
    if (!editable || busy || !dirty || !manual || needsBooleanChoice) return;
    setBusy(true);
    setError(null);
    setSaved(false);
    try {
      const result = await setAttribute(
        projectId,
        revisionId,
        row.equipment_id,
        row.attribute_key,
        {
          information_state: draft.state as ManualState,
          ...(present
            ? {
                value:
                  definition.value_type === "BOOLEAN"
                    ? draft.value === "true"
                    : numeric
                      ? draft.value.trim()
                      : draft.value,
                ...(numeric && draft.unit ? { unit: draft.unit } : {}),
              }
            : {}),
        },
      );
      setRow(result);
      setDraft(draftOf(result));
      setSaved(true);
    } catch (err) {
      setError(apiErrorOf(err).detail);
      failed(err);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Card className="p-4">
      <form
        onSubmit={save}
        className="space-y-3"
        aria-label={definition.display_name}
      >
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="font-semibold">{definition.display_name}</h3>
          {definition.required && <Chip>Required</Chip>}
          {definition.critical && <Chip>Critical</Chip>}
          {(definition.requirement_group ||
            definition.requirement_condition) && <Chip>Conditional</Chip>}
        </div>
        {definition.notes && (
          <p className="text-xs text-slate-500">{definition.notes}</p>
        )}
        {definition.requirement_condition && (
          <p className="text-xs text-slate-500">
            {definition.requirement_condition}
          </p>
        )}
        <ModelSelect
          label="Information state"
          value={draft.state}
          disabled={!editable || busy}
          onChange={(state) => {
            setSaved(false);
            setDraft({
              ...draft,
              state: state as InformationState,
            });
          }}
        >
          {!manual && (
            <option value={draft.state} disabled>
              {draft.state === "NOT_EXTRACTED"
                ? "Not extracted"
                : "Conflicting"}
            </option>
          )}
          {states.map((s) => (
            <option key={s.value} value={s.value}>
              {s.label}
            </option>
          ))}
        </ModelSelect>
        {present && (
          <>
            {definition.value_type === "ENUM" ||
            definition.value_type === "BOOLEAN" ? (
              <ModelSelect
                label="Value"
                value={draft.value}
                disabled={!editable || busy}
                onChange={(value) => setDraft({ ...draft, value })}
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
              </ModelSelect>
            ) : (
              <Field id={id} label="Value">
                <Input
                  id={id}
                  value={draft.value}
                  disabled={!editable || busy}
                  inputMode={
                    numeric
                      ? definition.value_type === "INTEGER"
                        ? "numeric"
                        : "decimal"
                      : "text"
                  }
                  onChange={(e) =>
                    setDraft({ ...draft, value: e.target.value })
                  }
                />
              </Field>
            )}
            {numeric && definition.supported_input_units.length > 0 && (
              <ModelSelect
                label="Input unit"
                value={draft.unit}
                disabled={!editable || busy}
                onChange={(unit) => setDraft({ ...draft, unit })}
              >
                {definition.supported_input_units.map((unit) => (
                  <option key={unit} value={unit}>
                    {unit}
                  </option>
                ))}
              </ModelSelect>
            )}
            {numeric && (
              <p className="text-xs text-slate-500">
                Changing the unit changes how your input is interpreted.
                Conversion occurs on save.
              </p>
            )}
          </>
        )}
        <p className="text-xs text-slate-500">
          {row.origin ?? "No origin"} · {row.verification_state}
          {row.confidence != null ? ` · Confidence ${row.confidence}` : ""}
        </p>
        {error && <ModelNotice>{error}</ModelNotice>}
        {saved && (
          <p role="status" className="text-sm text-slate-600">
            Saved.
          </p>
        )}
        {editable && (
          <Button
            type="submit"
            size="sm"
            disabled={
              busy ||
              !dirty ||
              !manual ||
              needsBooleanChoice
            }
          >
            {busy ? "Saving…" : "Save attribute"}
          </Button>
        )}
      </form>
    </Card>
  );
}
