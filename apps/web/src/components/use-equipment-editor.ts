"use client";
import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useModel } from "@/components/model-shared";
import { apiErrorOf } from "@/lib/api";
import {
  getEquipmentEditor,
  saveEquipmentEditor,
  type EquipmentSnapshot,
} from "@/lib/engineering-model";
import {
  editorChanges,
  equipmentDraft,
  type EquipmentDraft,
} from "@/lib/equipment-draft";
import { keys } from "@/lib/query-keys";

/** Server-confirmed equipment snapshot query, shared by Quick Details and the editor. */
export function useEquipmentSnapshot(id: string, onMissing: () => void) {
  const { projectId, revisionId, failed } = useModel();
  const query = useQuery({
    queryKey: keys.editor(projectId, revisionId, id),
    queryFn: () => getEquipmentEditor(projectId, revisionId, id),
  });
  const callbacks = useRef({ onMissing, failed });
  callbacks.current = { onMissing, failed };
  const missing = useRef<() => boolean>(() => false);
  useEffect(() => {
    if (!query.error) return;
    if (apiErrorOf(query.error).status === 404 && !missing.current()) {
      callbacks.current.onMissing();
      callbacks.current.failed(query.error);
    }
  }, [query.error]);
  return { query, missing };
}

/** One protected draft for General, Attributes and Terminals, saved atomically. */
export function useEquipmentEditor(
  id: string,
  onMissing: () => void,
  active = true,
) {
  const { projectId, revisionId, registry, writable, changed, failed } =
    useModel();
  const { query, missing } = useEquipmentSnapshot(id, onMissing);
  const [snapshot, setSnapshot] = useState<EquipmentSnapshot | null>(null);
  const [draft, setDraft] = useState<EquipmentDraft | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const client = useQueryClient();
  const dirtyRef = useRef(false);
  missing.current = () => dirtyRef.current;
  useEffect(() => {
    if (query.data && !dirtyRef.current) {
      setSnapshot(query.data);
      setDraft(equipmentDraft(query.data));
    }
  }, [query.data]);
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
    writable &&
    snapshot?.equipment.lifecycle_status === "ACTIVE" &&
    query.data?.equipment.lifecycle_status === "ACTIVE";
  const canSave = !!editable && changes.dirty && !changes.invalid && !busy;
  async function save() {
    if (!canSave) return false;
    setBusy(true);
    setError(null);
    try {
      const fresh = await saveEquipmentEditor(
        projectId,
        revisionId,
        id,
        changes.body,
      );
      await client.cancelQueries({
        queryKey: keys.editor(projectId, revisionId, id),
      });
      setSnapshot(fresh);
      client.setQueryData(keys.editor(projectId, revisionId, id), fresh);
      setDraft(equipmentDraft(fresh));
      dirtyRef.current = false;
      changed();
      return true;
    } catch (err) {
      setError(apiErrorOf(err).detail);
      failed(err);
      return false;
    } finally {
      setBusy(false);
    }
  }
  const saveRef = useRef(save);
  saveRef.current = save;
  const activeRef = useRef(active);
  activeRef.current = active;
  useEffect(() => {
    const key = (event: KeyboardEvent) => {
      if (
        activeRef.current &&
        (event.ctrlKey || event.metaKey) &&
        event.key.toLowerCase() === "s"
      ) {
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
  return {
    query,
    snapshot,
    draft,
    setDraft,
    definitions,
    changes,
    editable: !!editable,
    canSave,
    busy,
    error,
    save,
  };
}
