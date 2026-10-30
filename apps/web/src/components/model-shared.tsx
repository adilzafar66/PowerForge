"use client";

import { Select } from "@/components/ui/select";

import {
  createContext,
  useContext,
  useId,
  useState,
  type ReactNode,
} from "react";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Field } from "@/components/ui/field";
import { fieldClassName } from "@/components/ui/input";
import { Sheet } from "@/components/ui/sheet";
import { SegmentedControl } from "@/components/ui/segmented-control";
import type { LifecycleFilter, Registry } from "@/lib/engineering-model";
import { AsyncState } from "@/components/ui/async-state";

export type ModelContextValue = {
  projectId: string;
  revisionId: string;
  registry: Registry;
  writable: boolean;
  changed: () => void;
  failed: (error: unknown) => void;
};
export const ModelContext = createContext<ModelContextValue | null>(null);
export function useModel() {
  const value = useContext(ModelContext);
  if (!value) throw new Error("Model workspace is required");
  return value;
}

export function ModelNotice({ children }: { children: ReactNode }) {
  return (
    <p
      role="alert"
      className="my-3 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900"
    >
      {children}
    </p>
  );
}
export function LoadState({
  loading,
  error,
  retry,
  refreshing = false,
}: {
  loading: boolean;
  error: string | null;
  retry: () => void;
  refreshing?: boolean;
}) {
  return (
    <AsyncState
      pending={loading}
      refreshing={refreshing}
      error={error ? new Error(error) : null}
      retry={retry}
    />
  );
}
export function ModelSelect({
  label,
  value,
  onChange,
  children,
  disabled = false,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  children: ReactNode;
  disabled?: boolean;
}) {
  const id = useId();
  return (
    <Field id={id} label={label}>
      <Select
        id={id}
        className={fieldClassName}
        value={value}
        disabled={disabled}
        onValueChange={(value) => onChange(value)}
      >
        {children}
      </Select>
    </Field>
  );
}
export function ModelSheet({
  title,
  onClose,
  children,
  actions,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
  actions?: ReactNode;
}) {
  const id = useId();
  return (
    <Sheet labelledBy={id} onClose={onClose} className="md:max-w-[42rem]">
      <header className="sticky top-0 z-10 flex shrink-0 items-center justify-between gap-3 border-b border-slate-100 bg-white p-5">
        <h2 id={id} className="text-lg font-semibold">
          {title}
        </h2>
        <div className="ml-auto flex items-center gap-2">
          {actions}
          <Button variant="ghost" onClick={onClose}>
            Close
          </Button>
        </div>
      </header>
      <div className="overflow-y-auto p-5 space-y-5">{children}</div>
    </Sheet>
  );
}
export function LifecycleControl({
  value,
  onChange,
}: {
  value: LifecycleFilter;
  onChange: (value: LifecycleFilter) => void;
}) {
  return (
    <SegmentedControl
      label="Lifecycle"
      value={value}
      onChange={onChange}
      options={[
        { value: "ACTIVE", label: "Active" },
        { value: "REMOVED", label: "Removed" },
        { value: "ALL", label: "All" },
      ]}
    />
  );
}
export const NODE_REMOVE_WARNING =
  "Removing this node or terminal also removes active connections incident to it. Restoring it does not automatically restore those connections.";
export const EQUIPMENT_REMOVE_WARNING =
  "Removing this equipment also removes its terminal nodes and active incident connections. Restoring the equipment restores its terminals, but does not automatically restore those connections.";

export function ModelAction({
  label,
  action,
  warning,
  disabled = false,
}: {
  label: string;
  action: () => Promise<unknown>;
  warning?: string;
  disabled?: boolean;
}) {
  const { writable, changed, failed } = useModel();
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  if (!writable) return null;
  async function run() {
    if (busy || disabled || !writable) return;
    setConfirm(false);
    setBusy(true);
    try {
      await action();
      changed();
    } catch (error) {
      failed(error);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <Button
        size="sm"
        variant="outline"
        disabled={busy || disabled}
        onClick={() => (warning ? setConfirm(true) : void run())}
      >
        {busy ? "Saving…" : label}
      </Button>
      {confirm && (
        <ConfirmDialog
          title={`${label}?`}
          message={warning!}
          confirmLabel={label}
          danger
          onCancel={() => setConfirm(false)}
          onConfirm={() => void run()}
        />
      )}
    </>
  );
}
