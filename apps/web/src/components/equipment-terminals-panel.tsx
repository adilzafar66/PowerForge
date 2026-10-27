"use client";
import { useId } from "react";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { NODE_REMOVE_WARNING } from "@/components/model-shared";
import type { TerminalDraft } from "@/lib/equipment-draft";

export function EquipmentTerminalsPanel({
  terminals,
  onChange,
  editable,
}: {
  terminals: TerminalDraft[];
  onChange: (terminals: TerminalDraft[]) => void;
  editable: boolean;
}) {
  const id = useId();
  const update = (index: number, patch: Partial<TerminalDraft>) =>
    onChange(terminals.map((n, i) => (i === index ? { ...n, ...patch } : n)));
  return (
    <div className="space-y-4">
      <p className="text-sm text-slate-500">
        Normal terminals are application-managed. Add custom terminals only for
        exceptional roles such as Ground or Neutral.
      </p>
      {editable && (
        <Button
          onClick={() =>
            onChange([
              ...terminals,
              {
                id: crypto.randomUUID(),
                terminal_key: "",
                label: "",
                lifecycle_status: "ACTIVE",
                managed_by_profile: false,
                isNew: true,
              },
            ])
          }
        >
          Add Custom Terminal
        </Button>
      )}
      {terminals.map((n, index) => (
        <section
          role="group"
          key={n.id}
          aria-label={`Terminal ${n.terminal_key || "new"}`}
          className="space-y-3 rounded-lg border p-4"
        >
          <p className="text-sm">
            {n.managed_by_profile ? "Application-managed" : "Custom"} ·{" "}
            {n.lifecycle_status === "ACTIVE" ? "Active" : "Removed"}
          </p>
          <Field id={`${id}-${index}-key`} label="Terminal key">
            <Input
              id={`${id}-${index}-key`}
              value={n.terminal_key}
              disabled={
                !editable ||
                n.managed_by_profile ||
                n.lifecycle_status === "REMOVED"
              }
              onChange={(e) => update(index, { terminal_key: e.target.value })}
            />
          </Field>
          <Field id={`${id}-${index}-label`} label="Label">
            <Input
              id={`${id}-${index}-label`}
              value={n.label}
              disabled={!editable || n.lifecycle_status === "REMOVED"}
              onChange={(e) => update(index, { label: e.target.value })}
            />
          </Field>
          {editable && !n.managed_by_profile && (
            <Button
              variant="outline"
              onClick={() =>
                n.isNew
                  ? onChange(terminals.filter((t) => t.id !== n.id))
                  : update(index, {
                      lifecycle_status:
                        n.lifecycle_status === "ACTIVE" ? "REMOVED" : "ACTIVE",
                    })
              }
            >
              {n.lifecycle_status === "ACTIVE"
                ? "Remove terminal"
                : "Restore terminal"}
            </Button>
          )}
          {n.lifecycle_status === "REMOVED" && (
            <p className="text-xs text-slate-500">{NODE_REMOVE_WARNING}</p>
          )}
        </section>
      ))}
    </div>
  );
}
