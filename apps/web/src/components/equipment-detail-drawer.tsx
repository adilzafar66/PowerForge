"use client";
import { useEffect, useId, useRef, useState } from "react";
import { AttributeEditor } from "@/components/equipment-attributes-panel";
import { EquipmentTerminalsPanel } from "@/components/equipment-terminals-panel";
import {
  EQUIPMENT_REMOVE_WARNING,
  ModelAction,
  ModelNotice,
  ModelSelect,
  ModelSheet,
  useModel,
} from "@/components/model-shared";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input, Textarea } from "@/components/ui/input";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { apiErrorOf } from "@/lib/api";
import {
  equipmentLabel,
  getEquipmentEditor,
  saveEquipmentEditor,
  removeEquipment,
  restoreEquipment,
  type EquipmentSnapshot,
} from "@/lib/engineering-model";
import {
  equipmentDraft,
  editorChanges,
  type EquipmentDraft,
} from "@/lib/equipment-draft";

export function EquipmentDetailDrawer({
  id,
  onClose,
}: {
  id: string;
  onClose: () => void;
}) {
  const {
    projectId,
    revisionId,
    registry,
    version,
    writable,
    changed,
    failed,
  } = useModel();
  const [snapshot, setSnapshot] = useState<EquipmentSnapshot | null>(null);
  const [draft, setDraft] = useState<EquipmentDraft | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState("general");
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [retry, setRetry] = useState(0);
  const fieldId = useId();
  const dirtyRef = useRef(false);
  const callbacks = useRef({ onClose, failed });
  callbacks.current = { onClose, failed };
  useEffect(() => {
    let current = true;
    getEquipmentEditor(projectId, revisionId, id)
      .then((value) => {
        if (current && !dirtyRef.current) {
          setSnapshot(value);
          setDraft(equipmentDraft(value));
          setError(null);
        }
      })
      .catch((err) => {
        if (current) {
          setError(apiErrorOf(err).detail);
          if (apiErrorOf(err).status === 404 && !dirtyRef.current)
            callbacks.current.onClose();
          callbacks.current.failed(err);
        }
      });
    return () => {
      current = false;
    };
  }, [projectId, revisionId, id, version, retry]);
  const definitions =
    registry.equipment_types.find(
      (t) => t.key === snapshot?.equipment.equipment_type,
    )?.attributes ?? [];
  const changes =
    snapshot && draft
      ? editorChanges(snapshot, draft, definitions)
      : { body: {}, dirty: false, invalid: false };
  dirtyRef.current = changes.dirty;
  const editable =
    writable && snapshot?.equipment.lifecycle_status === "ACTIVE";
  const canSave = !!editable && changes.dirty && !changes.invalid && !busy;
  async function save(close = false) {
    if (!canSave) return;
    setBusy(true);
    setError(null);
    try {
      const fresh = await saveEquipmentEditor(
        projectId,
        revisionId,
        id,
        changes.body,
      );
      setSnapshot(fresh);
      setDraft(equipmentDraft(fresh));
      dirtyRef.current = false;
      setConfirm(false);
      changed();
      if (close) onClose();
    } catch (err) {
      setError(apiErrorOf(err).detail);
      failed(err);
    } finally {
      setBusy(false);
    }
  }
  const saveRef = useRef(save);
  saveRef.current = save;
  useEffect(() => {
    const key = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
        event.preventDefault();
        void saveRef.current();
      }
    };
    const unload = (event: BeforeUnloadEvent) => {
      if (dirtyRef.current) {
        event.preventDefault();
        event.returnValue = "";
      }
    };
    document.addEventListener("keydown", key);
    window.addEventListener("beforeunload", unload);
    return () => {
      document.removeEventListener("keydown", key);
      window.removeEventListener("beforeunload", unload);
    };
  }, []);
  function close() {
    if (busy) return;
    if (changes.dirty) setConfirm(true);
    else onClose();
  }
  return (
    <ModelSheet
      title={
        snapshot
          ? equipmentLabel(snapshot.equipment, registry)
          : "Equipment details"
      }
      onClose={close}
      actions={
        <Button disabled={!canSave} onClick={() => void save()}>
          {busy ? "Saving…" : "Save"}
        </Button>
      }
    >
      {error && (
        <ModelNotice>
          {error}{" "}
          {!snapshot && (
            <Button onClick={() => setRetry((v) => v + 1)}>Retry</Button>
          )}
        </ModelNotice>
      )}
      {!snapshot && !error && <p role="status">Loading equipment…</p>}
      {snapshot && draft && (
        <>
          <div className="flex items-center gap-3">
            <span>{snapshot.equipment.lifecycle_status}</span>
            <ModelAction
              label={
                snapshot.equipment.lifecycle_status === "ACTIVE"
                  ? "Remove equipment"
                  : "Restore equipment"
              }
              disabled={changes.dirty || busy}
              warning={
                snapshot.equipment.lifecycle_status === "ACTIVE"
                  ? EQUIPMENT_REMOVE_WARNING
                  : undefined
              }
              action={() =>
                snapshot.equipment.lifecycle_status === "ACTIVE"
                  ? removeEquipment(projectId, revisionId, id)
                  : restoreEquipment(projectId, revisionId, id)
              }
            />
          </div>
          <p className="text-xs text-slate-500">
            Origin: {snapshot.equipment.origin} · Verification:{" "}
            {snapshot.equipment.verification_state}
          </p>
          <SegmentedControl
            label="Equipment detail"
            value={tab}
            onChange={setTab}
            options={[
              { value: "general", label: "General" },
              { value: "attributes", label: "Attributes" },
              { value: "terminals", label: "Terminals" },
            ]}
          />
          {tab === "general" && (
            <div className="space-y-4">
              <ModelSelect
                label="Equipment Type"
                value={draft.general.equipment_type}
                disabled={!editable || busy}
                onChange={(equipment_type) =>
                  setDraft({
                    ...draft,
                    general: { ...draft.general, equipment_type },
                  })
                }
              >
                {registry.equipment_types.map((t) => (
                  <option key={t.key} value={t.key}>
                    {t.display_name}
                  </option>
                ))}
              </ModelSelect>
              {draft.general.equipment_type !==
                snapshot.equipment.equipment_type && (
                <p className="text-sm text-slate-500">
                  Save to reconcile attributes and normal terminals for the new
                  type. Changes that would discard meaningful data or active
                  connections will be rejected.
                </p>
              )}
              {(["tag", "name", "description"] as const).map((key) => (
                <Field
                  key={key}
                  id={`${fieldId}-${key}`}
                  label={key[0].toUpperCase() + key.slice(1)}
                >
                  {key === "description" ? (
                    <Textarea
                      id={`${fieldId}-${key}`}
                      value={draft.general[key]}
                      disabled={!editable || busy}
                      onChange={(e) =>
                        setDraft({
                          ...draft,
                          general: { ...draft.general, [key]: e.target.value },
                        })
                      }
                    />
                  ) : (
                    <Input
                      id={`${fieldId}-${key}`}
                      value={draft.general[key]}
                      disabled={!editable || busy}
                      onChange={(e) =>
                        setDraft({
                          ...draft,
                          general: { ...draft.general, [key]: e.target.value },
                        })
                      }
                    />
                  )}
                </Field>
              ))}
            </div>
          )}
          {tab === "attributes" && (
            <div className="space-y-4">
              {definitions.map((definition) => {
                const row = snapshot.attributes.find(
                  (a) => a.attribute_key === definition.key,
                );
                return (
                  row && (
                    <AttributeEditor
                      key={row.id}
                      definition={definition}
                      initial={row}
                      draft={draft.attributes[row.attribute_key]}
                      setDraft={(value) =>
                        setDraft({
                          ...draft,
                          attributes: {
                            ...draft.attributes,
                            [row.attribute_key]: value,
                          },
                        })
                      }
                      editable={!!editable && !busy}
                    />
                  )
                );
              })}
            </div>
          )}
          {tab === "terminals" && (
            <EquipmentTerminalsPanel
              terminals={draft.terminals}
              onChange={(terminals) => setDraft({ ...draft, terminals })}
              editable={!!editable && !busy}
            />
          )}
        </>
      )}
      {confirm && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="Unsaved changes"
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/25"
          onKeyDown={(e) => {
            if (e.key === "Escape") {
              e.preventDefault();
              e.stopPropagation();
              if (!busy) setConfirm(false);
            }
          }}
        >
          <div className="max-w-md space-y-4 rounded-xl bg-white p-6 shadow-xl">
            <h3 className="font-semibold">Save changes before closing?</h3>
            <p>Your equipment has unsaved changes.</p>
            {error && <ModelNotice>{error}</ModelNotice>}
            <div className="flex flex-wrap gap-2">
              <Button disabled={!canSave} onClick={() => void save(true)}>
                Save changes
              </Button>
              <Button variant="outline" disabled={busy} onClick={onClose}>
                Discard changes
              </Button>
              <Button
                variant="ghost"
                disabled={busy}
                onClick={() => setConfirm(false)}
              >
                Keep editing
              </Button>
            </div>
          </div>
        </div>
      )}
    </ModelSheet>
  );
}
