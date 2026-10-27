"use client";

import { useId, useState, type FormEvent } from "react";
import { ModelNotice, ModelSelect, useModel } from "@/components/model-shared";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input, Textarea } from "@/components/ui/input";
import { apiErrorOf } from "@/lib/api";
import { createEquipment, type Equipment } from "@/lib/engineering-model";

export function EquipmentGeneralPanel({
  onSaved,
}: {
  onSaved: (row: Equipment) => void;
}) {
  const { projectId, revisionId, registry, writable, changed, failed } =
    useModel();
  const id = useId();
  const [type, setType] = useState(registry.equipment_types[0]?.key ?? "");
  const [draft, setDraft] = useState({
    tag: "",
    name: "",
    description: "",
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const editable = writable;
  async function save(e: FormEvent) {
    e.preventDefault();
    if (!editable || saving) return;
    setSaving(true);
    setError(null);
    try {
      const saved = await createEquipment(projectId, revisionId, {
        ...draft,
        equipment_type: type,
      });
      changed();
      onSaved(saved);
    } catch (err) {
      setError(apiErrorOf(err).detail);
      failed(err);
    } finally {
      setSaving(false);
    }
  }
  return (
    <form onSubmit={save} className="space-y-4">
      <ModelSelect
        label="Equipment Type"
        value={type}
        onChange={setType}
        disabled={!editable || saving}
      >
        {registry.equipment_types.map((t) => (
          <option key={t.key} value={t.key}>
            {t.display_name}
          </option>
        ))}
      </ModelSelect>
      {(["tag", "name", "description"] as const).map((key) => (
        <Field
          key={key}
          id={`${id}-${key}`}
          label={key[0].toUpperCase() + key.slice(1)}
        >
          {key === "description" ? (
            <Textarea
              id={`${id}-${key}`}
              value={draft[key]}
              disabled={!editable || saving}
              onChange={(e) => setDraft({ ...draft, [key]: e.target.value })}
            />
          ) : (
            <Input
              id={`${id}-${key}`}
              value={draft[key]}
              disabled={!editable || saving}
              onChange={(e) => setDraft({ ...draft, [key]: e.target.value })}
            />
          )}
        </Field>
      ))}
      {error && <ModelNotice>{error}</ModelNotice>}
      {editable && (
        <Button type="submit" disabled={saving || !type}>
          {saving ? "Saving…" : "Create Equipment"}
        </Button>
      )}
    </form>
  );
}
