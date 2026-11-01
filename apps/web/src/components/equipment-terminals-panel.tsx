"use client";
import { Plus } from "lucide-react";
import { GroupTitle } from "@/components/equipment-ui";
import { NODE_REMOVE_WARNING } from "@/components/model-shared";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { TerminalDraft } from "@/lib/equipment-draft";
import { cn } from "@/lib/utils";

const grid =
  "grid grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)_minmax(0,1fr)] items-center gap-[11px] px-[15px] py-[13px] max-[700px]:grid-cols-1";
const control =
  "min-h-[37px] w-full min-w-0 rounded-[7px] border-border bg-panel px-[9px] py-[7px] text-workspace-caption text-ink disabled:bg-[var(--pf-control-disabled)] disabled:text-[#8c9aa8] disabled:opacity-100";

export function EquipmentTerminalsPanel({
  terminals,
  onChange,
  editable,
}: {
  terminals: TerminalDraft[];
  onChange: (terminals: TerminalDraft[]) => void;
  editable: boolean;
}) {
  const update = (index: number, patch: Partial<TerminalDraft>) =>
    onChange(terminals.map((n, i) => (i === index ? { ...n, ...patch } : n)));
  return (
    <>
      <GroupTitle title="Equipment terminals">
        Profile-managed and custom
      </GroupTitle>
      <p className="mt-0 mb-[18px] text-workspace-caption leading-[var(--pf-leading-relaxed)] text-muted">
        Normal terminals are application-managed. Add a custom terminal only for
        exceptional roles such as Ground or Neutral.
      </p>
      <div>
        <div
          aria-hidden
          className={cn(
            grid,
            "rounded-t-[var(--pf-radius-control)] border border-border bg-soft text-workspace-overline font-bold tracking-[0.8px] text-muted uppercase max-[700px]:hidden",
          )}
        >
          <span>Terminal key</span>
          <span>Label</span>
          <span>Management</span>
        </div>
        {terminals.length === 0 && (
          <p className="m-0 rounded-b-[var(--pf-radius-control)] border border-t-0 border-border px-[15px] py-[13px] text-workspace-caption text-muted max-[700px]:rounded-[var(--pf-radius-control)] max-[700px]:border-t">
            This equipment has no terminals.
          </p>
        )}
        {terminals.map((n, index) => {
          const removed = n.lifecycle_status === "REMOVED";
          return (
            <section
              role="group"
              key={n.id}
              aria-label={`Terminal ${n.terminal_key || "new"}`}
              className={cn(
                "border-x border-b border-border last-of-type:rounded-b-[var(--pf-radius-control)] max-[700px]:first-of-type:rounded-t-[var(--pf-radius-control)] max-[700px]:first-of-type:border-t",
                removed && "bg-canvas",
              )}
            >
              <div className={grid}>
                {n.managed_by_profile ? (
                  <strong
                    className={cn(
                      "text-workspace-caption font-semibold [overflow-wrap:anywhere] text-ink",
                      removed && "text-muted line-through",
                    )}
                  >
                    {n.terminal_key}
                  </strong>
                ) : (
                  <Input
                    aria-label="Terminal key"
                    aria-invalid={!removed && !n.terminal_key.trim()}
                    placeholder="Terminal key"
                    className={control}
                    value={n.terminal_key}
                    disabled={!editable || removed}
                    onChange={(e) =>
                      update(index, { terminal_key: e.target.value })
                    }
                  />
                )}
                <Input
                  aria-label="Label"
                  placeholder="Optional display label"
                  className={control}
                  value={n.label}
                  disabled={!editable || removed}
                  onChange={(e) => update(index, { label: e.target.value })}
                />
                <div className="flex min-w-0 flex-wrap items-center gap-2">
                  <span className="inline-flex rounded-[5px] bg-soft px-[6px] py-[3px] text-[10.5px] leading-[1.3] font-semibold text-muted">
                    {n.isNew
                      ? "Custom · New"
                      : `${n.managed_by_profile ? "Application-managed" : "Custom"} · ${removed ? "Removed" : "Active"}`}
                  </span>
                  {editable && !n.managed_by_profile && (
                    <Button
                      presentation="workspace"
                      size="sm"
                      variant={removed ? "outline" : "ghost"}
                      onClick={() =>
                        n.isNew
                          ? onChange(terminals.filter((t) => t.id !== n.id))
                          : update(index, {
                              lifecycle_status: removed ? "ACTIVE" : "REMOVED",
                            })
                      }
                    >
                      {removed ? "Restore terminal" : "Remove terminal"}
                    </Button>
                  )}
                </div>
              </div>
              {removed && (
                <p className="m-0 px-[15px] pb-[13px] text-[11.5px] leading-[1.4] text-muted">
                  {NODE_REMOVE_WARNING}
                </p>
              )}
            </section>
          );
        })}
      </div>
      <hr className="my-[23px] border-0 border-t border-border" />
      {editable && (
        <Button
          presentation="workspace"
          className="min-h-[39px] px-4"
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
          <Plus aria-hidden strokeWidth={1.7} />
          Add Custom Terminal
        </Button>
      )}
      <p className="mt-[14px] mb-0 rounded-[var(--pf-radius-control)] border border-border bg-[var(--pf-surface-note)] px-[15px] py-[13px] text-workspace-caption leading-[var(--pf-leading-hint)] text-muted">
        Equipment-type changes cannot remove terminals with active connections.
        Removing a terminal also removes its active connections, and restoring
        it does not restore them. Terminal changes are saved with the rest of
        the editor.
      </p>
    </>
  );
}
