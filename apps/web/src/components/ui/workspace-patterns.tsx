import { Card } from "@/components/ui/card";
import {
  Fragment,
  type ComponentProps,
  type HTMLAttributes,
  type ReactNode,
} from "react";
import { Checkbox } from "@/components/ui/checkbox";
import { cn } from "@/lib/utils";
import { X } from "lucide-react";

export type WorkspaceDetail = {
  label: string;
  value: ReactNode;
  /** Presentation only; callers own formatting and exact numeric serialization. */
  mono?: boolean;
};

/** A semantic description list; callers decide how missing values are presented. */
export function WorkspaceDetails({
  items,
  variant = "default",
}: {
  items: readonly WorkspaceDetail[];
  variant?: "default" | "project";
}) {
  return (
    <dl
      className={cn(
        "grid grid-cols-[var(--pf-detail-label-width)_minmax(0,_1fr)] gap-x-[18px] m-0 max-[790px]:grid-cols-[var(--pf-detail-mobile-label-width)_minmax(0,_1fr)]",
        variant === "project" &&
          "grid-cols-[var(--pf-detail-project-label-width)_minmax(0,_1fr)] gap-x-[0] max-[790px]:grid-cols-[var(--pf-detail-mobile-label-width)_minmax(0,_1fr)]",
      )}
    >
      {items.map(({ label, value, mono }) => (
        <Fragment key={label}>
          <dt
            className={cn(
              "py-[13px] px-0 m-0 border-b border-[var(--pf-border-row)] text-workspace-caption leading-[var(--pf-leading-copy)] [overflow-wrap:anywhere] text-muted font-semibold last-of-type:border-b-0",
              variant === "project" &&
                "py-[14px] px-[3px] text-workspace-label",
              "leading-[var(--pf-leading-copy)]",
            )}
          >
            {label}
          </dt>
          <dd
            className={cn(
              "py-[13px] px-0 m-0 border-b border-[var(--pf-border-row)] text-workspace-body leading-[var(--pf-leading-copy)] [overflow-wrap:anywhere] last-of-type:border-b-0",
              variant === "project" && "py-[14px] px-[3px] text-workspace-body",
              "leading-[var(--pf-leading-copy)]",
              mono && "font-mono",
            )}
          >
            {value}
          </dd>
        </Fragment>
      ))}
    </dl>
  );
}

/** Card anatomy for creation forms; does not own form state or submit behavior. */
export function WorkspaceFormSection({
  title,
  description,
  children,
  bodyClassName,
  footer,
}: {
  title: string;
  description?: ReactNode;
  children: ReactNode;
  bodyClassName?: string;
  footer?: ReactNode;
}) {
  return (
    <Card presentation="workspace" as="article">
      <div className="pt-5 px-[22px] pb-0">
        <h2 className="text-workspace-section font-semibold tracking-[-0.2px] m-0">
          {title}
        </h2>
        {description && (
          <p className="text-muted text-workspace-label mt-[6px] mx-0 mb-0">
            {description}
          </p>
        )}
      </div>
      <div className={cn("p-[22px]", bodyClassName)}>{children}</div>
      {footer}
    </Card>
  );
}

/** Keep the native checkbox and its accessible props; only share label/help layout. */
export function WorkspaceCheckboxField({
  label,
  description,
  ...props
}: Omit<ComponentProps<typeof Checkbox>, "children"> & {
  label: ReactNode;
  description: ReactNode;
}) {
  return (
    <label className="flex items-start gap-[10px] p-3 border border-border rounded-[var(--pf-radius-control)] my-2 mx-0 text-muted text-workspace-caption font-semibold">
      <Checkbox {...props} />
      <span>
        <strong className="text-workspace-label text-ink">{label}</strong>
        <small className="block text-workspace-caption font-normal text-muted mt-[5px] leading-[var(--pf-leading-hint)]">
          {description}
        </small>
      </span>
    </label>
  );
}

export function WorkspaceDrawerHeader({
  titleId,
  presentation = "revision",
  title,
  subtitle,
  closeLabel,
  pending,
  onClose,
}: {
  titleId: string;
  presentation?: "project" | "revision";
  title: string;
  subtitle?: ReactNode;
  closeLabel: string;
  pending?: boolean;
  onClose: () => void;
}) {
  return (
    <div
      className={cn(
        "py-[27px] px-[29px] border-b border-border flex justify-between items-start gap-3 max-[530px]:p-5",
        presentation === "project" &&
          "px-6 py-[23px] max-[530px]:px-6 max-[530px]:py-[23px]",
      )}
    >
      <div>
        <h2
          id={titleId}
          className={cn(
            "text-workspace-editor font-semibold tracking-[-0.5px] mt-0 mx-0 mb-[6px]",
            presentation === "project" && "text-workspace-editor-compact",
          )}
        >
          {title}
        </h2>
        <p
          className={cn(
            "text-muted text-workspace-body leading-[var(--pf-leading-copy)]",
            presentation === "project" && "text-workspace-caption",
            "leading-[var(--pf-leading-copy)]",
          )}
        >
          {subtitle}
        </p>
      </div>
      <button
        type="button"
        className="w-[30px] h-[30px] shrink-0 border border-border rounded-[var(--pf-radius-sm)] grid place-items-center text-muted"
        aria-label={closeLabel}
        disabled={pending}
        onClick={onClose}
      >
        <X size={16} />
      </button>
    </div>
  );
}

export function WorkspaceFormActions({
  className,
  ...props
}: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      {...props}
      className={cn(
        "border-t border-border py-4 px-[25px] flex justify-end gap-[10px] max-[530px]:p-[14px]",
        className,
      )}
    />
  );
}

export function WorkspaceDrawerBody({
  presentation = "revision",
  className,
  ...props
}: HTMLAttributes<HTMLDivElement> & { presentation?: "project" | "revision" }) {
  return (
    <div
      {...props}
      className={cn(
        "py-[25px] px-[29px] overflow-y-auto flex-1 max-[530px]:p-5",
        presentation === "project" && "p-[22px] max-[530px]:p-[22px]",
        className,
      )}
    />
  );
}
export function WorkspaceCardHeader({
  title,
  subtitle,
  actions,
}: {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="py-5 px-[22px] border-b border-border flex items-center justify-between gap-[15px]">
      <div>
        <h2 className="text-workspace-section font-semibold tracking-[-0.2px] m-0">
          {title}
        </h2>
        {subtitle && (
          <p className="mt-[5px] mx-0 mb-0 text-muted text-workspace-caption">
            {subtitle}
          </p>
        )}
      </div>
      {actions}
    </div>
  );
}
export function WorkspaceStats({ action }: { action?: ReactNode }) {
  return (
    <div
      className="flex flex-wrap items-center gap-4 border-t border-border pt-[17px] mt-[19px]"
      aria-label="Workspace counts unavailable"
    >
      {["Documents", "Equipment", "Connections"].map((label) => (
        <div className="[flex:1_1_75px] min-w-0" key={label}>
          <strong
            className="block text-workspace-editor font-semibold"
            title="Count not provided by revision metadata"
          >
            —
          </strong>
          <small className="text-muted text-workspace-caption block mt-[5px]">
            {label}
          </small>
        </div>
      ))}
      {action}
    </div>
  );
}
