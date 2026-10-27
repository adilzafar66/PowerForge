"use client";
import { useId } from "react";
import { ModelSelect } from "@/components/model-shared";
import { Card } from "@/components/ui/card";
import { Chip } from "@/components/ui/chip";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import type {
  AttributeDefinition,
  EquipmentAttribute,
  InformationState,
  ManualState,
} from "@/lib/engineering-model";
import type { AttributeDraft } from "@/lib/equipment-draft";

const states: { value: ManualState; label: string }[] = [
  { value: "NOT_POPULATED", label: "Not populated" },
  { value: "PRESENT", label: "Present" },
  { value: "MISSING", label: "Missing" },
  { value: "NOT_APPLICABLE", label: "Not applicable" },
];
export function AttributeEditor({
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
  const id = useId();
  const present = draft.state === "PRESENT";
  const manual = states.some((s) => s.value === draft.state);
  const numeric =
    definition.value_type === "NUMBER" || definition.value_type === "INTEGER";
  return (
    <Card className="p-4">
      <section
        role="group"
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
          disabled={!editable}
          onChange={(state) => {
            setDraft({
              ...draft,
              state: state as InformationState,
            });
          }}
        >
          {!manual && (
            <option value={draft.state} disabled>
              Conflicting
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
                disabled={!editable}
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
                  disabled={!editable}
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
                disabled={!editable}
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
          {initial.origin ?? "No origin"} · {initial.verification_state}
          {initial.confidence != null
            ? ` · Confidence ${initial.confidence}`
            : ""}
        </p>
      </section>
    </Card>
  );
}
