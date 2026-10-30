"use client";
import {
  WorkspaceFormActions,
  WorkspaceDrawerHeader,
} from "@/components/ui/workspace-patterns";

import { useEffect, useId, useState, type ReactNode } from "react";
import { Sheet } from "@/components/ui/sheet";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { WorkspaceButton as Button } from "@/components/ui-c-workspace";
import { Check } from "lucide-react";

/** Local drafts stay mounted through refetch; close and unload require a decision. */
export function WorkspaceEditor({
  title,
  subtitle,
  dirty,
  pending,
  disabled,
  error,
  onClose,
  onSave,
  children,
}: {
  title: string;
  subtitle?: string;
  dirty: boolean;
  pending: boolean;
  disabled?: boolean;
  error?: string | null;
  onClose: () => void;
  onSave: () => void;
  children: ReactNode;
}) {
  const id = useId();
  const [discard, setDiscard] = useState(false);
  useEffect(() => {
    if (!dirty && !pending) return;
    const guard = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", guard);
    return () => window.removeEventListener("beforeunload", guard);
  }, [dirty, pending]);
  const close = () => {
    if (!pending) {
      if (dirty) setDiscard(true);
      else onClose();
    }
  };
  return (
    <Sheet
      autoFocusFirst
      overlayClassName="ui-c-overlay"
      labelledBy={id}
      onClose={close}
      className={`ui-c-sheet ${title === "Edit project" ? "project" : ""}`}
    >
      <WorkspaceDrawerHeader
        titleId={id}
        title={title}
        subtitle={subtitle}
        closeLabel="Close editor"
        pending={pending}
        onClose={close}
      />
      <form
        className="flex min-h-0 flex-1 flex-col"
        onSubmit={(event) => {
          event.preventDefault();
          if (!disabled && !pending && dirty) onSave();
        }}
      >
        <div className="ui-c-drawer-body space-y-5">
          {error && (
            <p role="alert" className="text-sm text-red-600">
              {error}
            </p>
          )}
          <fieldset disabled={pending} className="space-y-5">
            {children}
          </fieldset>
        </div>
        <WorkspaceFormActions>
          <Button
            type="button"
            variant="outline"
            onClick={close}
            disabled={pending}
          >
            Cancel
          </Button>
          <Button
            type="submit"
            variant="primary"
            pending={pending}
            disabled={disabled || !dirty}
          >
            <Check />
            Save changes
          </Button>
        </WorkspaceFormActions>
      </form>
      {discard && (
        <ConfirmDialog
          className="ui-c-dialog"
          title="Discard unsaved changes?"
          message="Your changes have not been saved."
          confirmLabel="Discard changes"
          danger
          onCancel={() => setDiscard(false)}
          onConfirm={onClose}
        />
      )}
    </Sheet>
  );
}
