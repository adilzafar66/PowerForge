"use client";
import { useState } from "react";
import { EquipmentEditor } from "@/components/equipment-editor";
import type { EquipmentTab } from "@/lib/workspace-navigation";

/** Test harness that mirrors the workspace's URL-driven editor guard. */
export function EquipmentEditorHarness({
  id,
  initialTab = "general",
  onLeft,
  onMissing = () => {},
  onNavigate = () => {},
}: {
  id: string;
  initialTab?: EquipmentTab;
  onLeft: () => void;
  onMissing?: () => void;
  onNavigate?: (href: string) => void;
}) {
  const [tab, setTab] = useState(initialTab);
  const [inUrl, setInUrl] = useState(true);
  const [dirty, setDirty] = useState(false);
  const [open, setOpen] = useState(true);
  if (open && !inUrl && !dirty) {
    setOpen(false);
    onLeft();
  }
  if (!open) return null;
  return (
    <EquipmentEditor
      id={id}
      tab={tab}
      active
      leaving={!inUrl}
      onDirtyChange={setDirty}
      onTab={setTab}
      onReturn={() => setInUrl(false)}
      onStay={() => setInUrl(true)}
      onDiscard={() => {
        setOpen(false);
        onLeft();
      }}
      onMissing={onMissing}
      onNavigate={onNavigate}
    />
  );
}
