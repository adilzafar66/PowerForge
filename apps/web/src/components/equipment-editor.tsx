"use client";
import {
  useEffect,
  useId,
  useRef,
  useState,
  type KeyboardEvent,
  type ReactNode,
} from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { ArrowLeft, Check } from "lucide-react";
import { EquipmentAttributesPanel } from "@/components/equipment-attributes-panel";
import { EquipmentTerminalsPanel } from "@/components/equipment-terminals-panel";
import {
  DetailPair,
  GroupTitle,
  LifecycleStatus,
} from "@/components/equipment-ui";
import {
  EQUIPMENT_REMOVE_WARNING,
  ModelAction,
  ModelNotice,
  useModel,
} from "@/components/model-shared";
import { useEquipmentEditor } from "@/components/use-equipment-editor";
import { AsyncState } from "@/components/ui/async-state";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input, Textarea } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import {
  equipmentLabel,
  removeEquipment,
  restoreEquipment,
  typeLabel,
} from "@/lib/engineering-model";
import { useNavigationBlocker } from "@/lib/navigation-guard";
import { cn } from "@/lib/utils";
import { EQUIPMENT_TABS, type EquipmentTab } from "@/lib/workspace-navigation";

const TAB_LABELS: Record<EquipmentTab, string> = {
  general: "General",
  attributes: "Attributes",
  terminals: "Terminals",
};

export function EquipmentEditor({
  id,
  tab,
  active,
  leaving,
  onDirtyChange,
  onTab,
  onReturn,
  onStay,
  onDiscard,
  onMissing,
  onNavigate,
}: {
  id: string;
  tab: EquipmentTab;
  /** False while another revision workspace is shown; the draft is retained. */
  active: boolean;
  /** The URL has left this editor while the draft is dirty. */
  leaving: boolean;
  onDirtyChange: (dirty: boolean) => void;
  onTab: (tab: EquipmentTab) => void;
  onReturn: () => void;
  onStay: () => void;
  onDiscard: () => void;
  onMissing: () => void;
  /** Continues a navigation that was held for the unsaved-changes dialog. */
  onNavigate: (href: string) => void;
}) {
  const { projectId, revisionId, registry, writable, revisionLabel } =
    useModel();
  const editor = useEquipmentEditor(id, onMissing, active);
  const { snapshot, draft, changes, editable, busy } = editor;
  const fieldId = useId();
  const dirty = changes.dirty;
  const reportDirty = useRef(onDirtyChange);
  reportDirty.current = onDirtyChange;
  useEffect(() => reportDirty.current(dirty), [dirty]);
  useEffect(() => () => reportDirty.current(false), []);
  const [pending, setPending] = useState<string | null>(null);
  useNavigationBlocker(dirty, setPending);
  const stay = () => (pending === null ? onStay() : setPending(null));
  const discard = () => {
    onDiscard();
    if (pending !== null) {
      setPending(null);
      onNavigate(pending);
    }
  };
  async function saveAndLeave() {
    const target = pending;
    if ((await editor.save()) && target !== null) {
      setPending(null);
      onNavigate(target);
    }
  }
  const row = snapshot?.equipment;
  const removed = row?.lifecycle_status === "REMOVED";
  const label = row ? equipmentLabel(row, registry) : "Equipment";
  const tabs = useRef<Record<string, HTMLButtonElement | null>>({});
  function tabKey(event: KeyboardEvent<HTMLButtonElement>) {
    const index = EQUIPMENT_TABS.indexOf(tab);
    const offset =
      event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
    if (!offset) return;
    event.preventDefault();
    const next =
      EQUIPMENT_TABS[
        (index + offset + EQUIPMENT_TABS.length) % EQUIPMENT_TABS.length
      ];
    onTab(next);
    tabs.current[next]?.focus();
  }
  const status = busy
    ? "Saving…"
    : !editable
      ? "Read-only"
      : dirty
        ? changes.invalid
          ? "Complete highlighted values to save"
          : "Unsaved changes"
        : "No unsaved changes";
  return (
    <div hidden={!active}>
      <header className="mb-[21px] flex items-center justify-between gap-5 max-[700px]:items-start">
        <div className="min-w-0">
          <button
            type="button"
            onClick={onReturn}
            className="inline-flex items-center gap-2 border-0 bg-transparent p-0 text-workspace-caption font-semibold text-accent hover:text-accent-hover"
          >
            <ArrowLeft
              aria-hidden
              className="h-[14px] w-[14px]"
              strokeWidth={1.7}
            />
            Back to Equipment
          </button>
          <h1 className="my-[7px] flex flex-wrap items-center gap-x-[10px] text-workspace-title leading-[1.2] font-bold tracking-[-0.025em] [overflow-wrap:anywhere]">
            {label}
            {row && (
              <LifecycleStatus status={row.lifecycle_status} variant="title" />
            )}
          </h1>
          <p className="m-0 text-workspace-body text-muted">
            {row
              ? [
                  typeLabel(registry, row.equipment_type),
                  row.name && row.name !== label ? row.name : null,
                  revisionLabel,
                ]
                  .filter(Boolean)
                  .join(" · ")
              : "Loading equipment…"}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-[10px] max-[700px]:flex-col max-[700px]:items-end">
          <span
            role="status"
            className={cn(
              "text-workspace-caption text-muted",
              dirty && editable && "text-[var(--pf-warning)]",
            )}
          >
            {status}
          </span>
          <Button
            presentation="workspace"
            variant="primary"
            className="min-h-[39px] px-4"
            pending={busy}
            disabled={!editor.canSave}
            onClick={() => void editor.save()}
          >
            <Check aria-hidden strokeWidth={1.7} />
            {busy ? "Saving…" : "Save changes"}
          </Button>
        </div>
      </header>
      {editor.error && (
        <ModelNotice>
          {editor.error}{" "}
          {!snapshot && (
            <Button onClick={() => void editor.query.refetch()}>Retry</Button>
          )}
        </ModelNotice>
      )}
      <AsyncState
        pending={!snapshot && editor.query.isPending}
        refreshing={!!snapshot && editor.query.isFetching}
        error={snapshot ? null : editor.query.error}
        retry={editor.query.refetch}
      />
      {snapshot && draft && row && (
        <div className="grid grid-cols-[minmax(0,1fr)_var(--pf-equipment-editor-aside)] items-start gap-[19px] max-[970px]:grid-cols-1">
          <section className="min-w-0 overflow-hidden rounded-[11px] border border-border bg-panel">
            <div
              role="tablist"
              aria-label="Equipment editor sections"
              className="flex items-center gap-[3px] overflow-x-auto border-b border-border px-[23px] max-[700px]:px-3"
            >
              {EQUIPMENT_TABS.map((value) => (
                <button
                  key={value}
                  ref={(node) => {
                    tabs.current[value] = node;
                  }}
                  type="button"
                  role="tab"
                  id={`${fieldId}-tab-${value}`}
                  aria-selected={tab === value}
                  aria-controls={`${fieldId}-panel`}
                  tabIndex={tab === value ? 0 : -1}
                  onClick={() => onTab(value)}
                  onKeyDown={tabKey}
                  className={cn(
                    "-mb-px border-0 border-b-2 border-transparent bg-transparent px-[18px] pt-[18px] pb-[15px] text-workspace-body font-semibold whitespace-nowrap text-muted transition-colors hover:text-ink",
                    tab === value &&
                      "border-accent text-accent hover:text-accent",
                  )}
                >
                  {TAB_LABELS[value]}
                </button>
              ))}
            </div>
            <div
              role="tabpanel"
              id={`${fieldId}-panel`}
              aria-labelledby={`${fieldId}-tab-${tab}`}
              className="p-[25px] max-[700px]:p-[18px]"
            >
              {(!writable || removed) && (
                <p className="mt-0 mb-[18px] rounded-[var(--pf-radius-control)] border border-border bg-canvas px-[13px] py-3 text-workspace-caption leading-[var(--pf-leading-hint)] text-muted">
                  {!writable
                    ? "This revision is read-only. Equipment details remain viewable but cannot be changed."
                    : "This equipment is removed. Restore it to make changes."}
                </p>
              )}
              {tab === "general" && (
                <>
                  <GroupTitle title="General information">
                    Changes saved together
                  </GroupTitle>
                  <div className="grid grid-cols-2 gap-[18px] max-[700px]:grid-cols-1">
                    <Field
                      id={`${fieldId}-type`}
                      presentation="workspace"
                      label="Equipment type"
                      hint={
                        draft.general.equipment_type !== row.equipment_type
                          ? "Save to reconcile attributes and normal terminals for the new type. Changes that would discard meaningful data or active connections will be rejected."
                          : "Changing type reconciles attributes and terminal profiles."
                      }
                    >
                      <Select
                        id={`${fieldId}-type`}
                        presentation="workspace"
                        value={draft.general.equipment_type}
                        disabled={!editable || busy}
                        onValueChange={(equipment_type) =>
                          editor.setDraft({
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
                      </Select>
                    </Field>
                    {(
                      [
                        ["tag", "Equipment tag"],
                        ["name", "Equipment name"],
                      ] as const
                    ).map(([key, text]) => (
                      <Field
                        key={key}
                        id={`${fieldId}-${key}`}
                        presentation="workspace"
                        label={text}
                      >
                        <Input
                          id={`${fieldId}-${key}`}
                          presentation="workspace"
                          value={draft.general[key]}
                          disabled={!editable || busy}
                          onChange={(e) =>
                            editor.setDraft({
                              ...draft,
                              general: {
                                ...draft.general,
                                [key]: e.target.value,
                              },
                            })
                          }
                        />
                      </Field>
                    ))}
                    <div className="flex flex-col gap-1.5">
                      <span
                        id={`${fieldId}-lifecycle`}
                        className="text-workspace-caption font-semibold text-muted"
                      >
                        Lifecycle status
                      </span>
                      <div
                        role="group"
                        aria-labelledby={`${fieldId}-lifecycle`}
                        className="flex min-h-[41px] items-center justify-between gap-3 rounded-[var(--pf-radius-control)] border border-border bg-[var(--pf-control-disabled)] py-1 pr-1 pl-3"
                      >
                        <LifecycleStatus
                          status={row.lifecycle_status}
                          variant="detail"
                        />
                        <ModelAction
                          label={
                            removed ? "Restore equipment" : "Remove equipment"
                          }
                          disabled={dirty || busy}
                          warning={
                            removed ? undefined : EQUIPMENT_REMOVE_WARNING
                          }
                          action={() =>
                            removed
                              ? restoreEquipment(projectId, revisionId, id)
                              : removeEquipment(projectId, revisionId, id)
                          }
                        />
                      </div>
                      {writable && dirty && (
                        <p className="m-0 text-[12px] text-muted">
                          Save or discard changes before changing lifecycle.
                        </p>
                      )}
                    </div>
                  </div>
                  <hr className="my-[23px] border-0 border-t border-border" />
                  <Field
                    id={`${fieldId}-description`}
                    presentation="workspace"
                    label="Description"
                  >
                    <Textarea
                      id={`${fieldId}-description`}
                      presentation="workspace-editor"
                      rows={4}
                      placeholder="Add equipment notes or context…"
                      className="min-h-[125px]"
                      value={draft.general.description}
                      disabled={!editable || busy}
                      onChange={(e) =>
                        editor.setDraft({
                          ...draft,
                          general: {
                            ...draft.general,
                            description: e.target.value,
                          },
                        })
                      }
                    />
                  </Field>
                </>
              )}
              {tab === "attributes" && (
                <EquipmentAttributesPanel
                  definitions={editor.definitions}
                  attributes={snapshot.attributes}
                  draft={draft.attributes}
                  onChange={(key, value) =>
                    editor.setDraft({
                      ...draft,
                      attributes: { ...draft.attributes, [key]: value },
                    })
                  }
                  editable={editable && !busy}
                />
              )}
              {tab === "terminals" && (
                <EquipmentTerminalsPanel
                  terminals={draft.terminals}
                  onChange={(terminals) =>
                    editor.setDraft({ ...draft, terminals })
                  }
                  editable={editable && !busy}
                />
              )}
            </div>
          </section>
          <aside className="min-w-0 space-y-4">
            <AsideCard title="Equipment information">
              <dl className="m-0 [&>div+div]:border-t [&>div+div]:border-[var(--pf-border-row)]">
                <DetailPair label="Equipment tag" muted={!row.tag}>
                  {row.tag || "Not provided"}
                </DetailPair>
                <DetailPair label="Type">
                  {typeLabel(registry, row.equipment_type)}
                </DetailPair>
                <DetailPair label="Lifecycle">
                  <LifecycleStatus
                    status={row.lifecycle_status}
                    variant="detail"
                  />
                </DetailPair>
                <DetailPair label="Origin">{row.origin}</DetailPair>
                <DetailPair label="Verification">
                  {row.verification_state}
                </DetailPair>
              </dl>
              <p className="mt-[13px] mb-0 rounded-[var(--pf-radius-control)] bg-selection p-3 text-workspace-caption leading-[var(--pf-leading-hint)] text-accent">
                <strong className="block font-semibold">
                  Single Save operation
                </strong>
                All sections save in one transaction. You’ll be warned before
                unsaved changes are discarded.
              </p>
            </AsideCard>
            <AsideCard title="Navigation">
              <p className="m-0 text-workspace-caption leading-[var(--pf-leading-relaxed)] text-muted">
                General, Attributes, and Terminals are edited in one workspace.
                Registry-driven fields remain precise and revision-scoped.
              </p>
            </AsideCard>
          </aside>
        </div>
      )}
      {editable && (
        <p className="mt-[14px] mb-0 flex items-center gap-[9px] text-workspace-caption text-muted">
          <Check aria-hidden className="h-[14px] w-[14px]" strokeWidth={1.7} />
          Press ⌘S or Ctrl+S to save all sections together.
        </p>
      )}
      <Dialog.Root
        open={leaving || pending !== null}
        onOpenChange={(open) => {
          if (!open && !busy) stay();
        }}
      >
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-[60] bg-[var(--pf-overlay-workspace)] animate-[workspace-appear_var(--pf-motion-overlay)_ease] motion-reduce:animate-none" />
          <Dialog.Content className="fixed top-1/2 left-1/2 z-[70] w-[calc(100%-32px)] max-w-[var(--pf-dialog-width-wide)] -translate-x-1/2 -translate-y-1/2 rounded-[var(--pf-radius-dialog)] border border-border bg-panel p-[25px] shadow-workspace-dialog">
            <Dialog.Title className="mb-3 text-workspace-subheading font-semibold text-ink">
              Unsaved changes
            </Dialog.Title>
            <Dialog.Description className="mb-5 text-workspace-label leading-[1.7] text-muted">
              {label} has unsaved changes. Save them, keep editing, or discard
              the draft.
            </Dialog.Description>
            {editor.error && <ModelNotice>{editor.error}</ModelNotice>}
            <div className="flex flex-wrap justify-end gap-2">
              <Button
                presentation="workspace-dialog"
                variant="ghost"
                disabled={busy}
                onClick={stay}
              >
                Keep editing
              </Button>
              <Button
                presentation="workspace-dialog"
                variant="outline"
                disabled={busy}
                onClick={discard}
              >
                Discard changes
              </Button>
              <Button
                presentation="workspace-dialog"
                variant="primary"
                disabled={!editor.canSave}
                onClick={() => void saveAndLeave()}
              >
                Save and leave
              </Button>
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </div>
  );
}

function AsideCard({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <section className="rounded-[11px] border border-border bg-panel px-[18px] pt-[18px] pb-[14px]">
      <h2 className="mt-0 mb-[14px] text-workspace-label font-semibold">
        {title}
      </h2>
      {children}
    </section>
  );
}
