"use client";
import { WorkspaceDrawerBody } from "@/components/ui/workspace-patterns";
import {
  WorkspaceFormActions,
  WorkspaceDrawerHeader,
} from "@/components/ui/workspace-patterns";
import { useEffect, useId, useState, type ReactNode } from "react";
import { Sheet } from "@/components/ui/sheet";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Button } from "@/components/ui/button";
import { Check } from "lucide-react";
/** Local drafts stay mounted through refetch; close and unload require a decision. */
export function WorkspaceEditor({
  presentation,
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
  presentation: "project" | "revision";
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
      labelledBy={id}
      onClose={close}
      presentation={
        presentation === "project" ? "workspace-project" : "workspace-revision"
      }
    >
      <WorkspaceDrawerHeader
        presentation={presentation}
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
        <WorkspaceDrawerBody presentation={presentation} className="space-y-5">
          {error && (
            <p role="alert" className="text-sm text-red-600">
              {error}
            </p>
          )}
          <fieldset disabled={pending} className="space-y-5">
            {children}
          </fieldset>
        </WorkspaceDrawerBody>
        <WorkspaceFormActions>
          <Button
            type="button"
            variant="outline"
            onClick={close}
            disabled={pending}
            presentation="workspace"
          >
            Cancel
          </Button>
          <Button
            type="submit"
            variant="primary"
            pending={pending}
            disabled={disabled || !dirty}
            presentation="workspace"
          >
            <Check />
            Save changes
          </Button>
        </WorkspaceFormActions>
      </form>
      {discard && (
        <ConfirmDialog
          title="Discard unsaved changes?"
          message="Your changes have not been saved."
          confirmLabel="Discard changes"
          danger
          onCancel={() => setDiscard(false)}
          onConfirm={onClose}
          presentation="workspace"
        />
      )}
    </Sheet>
  );
}
