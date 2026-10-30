import type { ReactNode } from "react";
import { Button } from "@/components/ui/button";
import "./ui-c-workspace.css";
export {
  WorkspaceCard,
  WorkspaceCardBody,
  WorkspaceDetails,
  WorkspaceFormSection,
  WorkspaceCheckboxField,
  WorkspaceDrawerHeader,
  WorkspaceFormActions,
} from "@/components/ui/workspace-patterns";

export function WorkspaceHeader({
  title,
  subtitle,
  actions,
}: {
  title: ReactNode;
  subtitle: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className="ui-c-head">
      <div className="ui-c-head-inner">
        <div>
          <h1>{title}</h1>
          <p className="ui-c-subtitle">{subtitle}</p>
        </div>
        <div className="ui-c-actions">{actions}</div>
      </div>
    </header>
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
    <div className="ui-c-card-top">
      <div>
        <h2>{title}</h2>
        {subtitle && <p>{subtitle}</p>}
      </div>
      {actions}
    </div>
  );
}
export function WorkspaceButton({
  className = "",
  variant = "outline",
  size,
  ...props
}: React.ComponentProps<typeof Button>) {
  return (
    <Button
      {...props}
      variant={variant}
      size={size}
      className={`ui-c-btn ${variant === "primary" ? "primary" : variant === "danger" ? "danger" : variant === "ghost" ? "quiet" : ""} ${size === "sm" ? "small" : ""} ${className}`}
    />
  );
}
export function WorkspaceStatus({ status }: { status: string }) {
  return (
    <span className={`ui-c-status ${status}`}>
      {status.charAt(0) + status.slice(1).toLowerCase()}
    </span>
  );
}
export function WorkspaceStats({ action }: { action?: ReactNode }) {
  return (
    <div className="ui-c-stats" aria-label="Workspace counts unavailable">
      {["Documents", "Equipment", "Connections"].map((label) => (
        <div className="ui-c-stat" key={label}>
          <strong title="Count not provided by revision metadata">—</strong>
          <small>{label}</small>
        </div>
      ))}
      {action}
    </div>
  );
}
