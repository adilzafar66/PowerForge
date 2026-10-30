import {
  Fragment,
  type ComponentProps,
  type HTMLAttributes,
  type ReactNode,
} from "react";
import { Checkbox } from "@/components/ui/checkbox";
import { cn } from "@/lib/utils";
import { X } from "lucide-react";
import "../ui-c-workspace.css";

/** Shared workspace surfaces. Variants preserve the approved content/rail density. */
export function WorkspaceCard({
  as: Element = "article",
  spacing = "none",
  className,
  ...props
}: HTMLAttributes<HTMLElement> & {
  as?: "article" | "section" | "div";
  spacing?: "none" | "body" | "rail" | "work";
}) {
  const padding = {
    none: "",
    body: "ui-c-pad",
    rail: "ui-c-rail",
    work: "ui-c-work",
  }[spacing];
  return <Element {...props} className={cn("ui-c-card", padding, className)} />;
}

export function WorkspaceCardBody({
  className,
  ...props
}: HTMLAttributes<HTMLDivElement>) {
  return <div {...props} className={cn("ui-c-pad", className)} />;
}

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
    <dl className={cn("ui-c-details", variant === "project" && "project")}>
      {items.map(({ label, value, mono }) => (
        <Fragment key={label}>
          <dt>{label}</dt>
          <dd className={mono ? "font-mono" : undefined}>{value}</dd>
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
    <WorkspaceCard>
      <div className="ui-c-form-head">
        <h2>{title}</h2>
        {description && <p>{description}</p>}
      </div>
      <div className={cn("ui-c-form-body", bodyClassName)}>{children}</div>
      {footer}
    </WorkspaceCard>
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
    <label className="ui-c-check">
      <Checkbox {...props} />
      <span>
        <strong>{label}</strong>
        <small>{description}</small>
      </span>
    </label>
  );
}

export function WorkspaceDrawerHeader({
  titleId,
  title,
  subtitle,
  closeLabel,
  pending,
  onClose,
}: {
  titleId: string;
  title: string;
  subtitle?: ReactNode;
  closeLabel: string;
  pending?: boolean;
  onClose: () => void;
}) {
  return (
    <div className="ui-c-drawer-head">
      <div>
        <h2 id={titleId}>{title}</h2>
        <p>{subtitle}</p>
      </div>
      <button
        type="button"
        className="ui-c-close"
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
  return <div {...props} className={cn("ui-c-drawer-foot", className)} />;
}
