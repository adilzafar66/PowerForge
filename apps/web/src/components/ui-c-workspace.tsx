import { workspaceStyles as ws } from "@/components/ui/workspace-styles";
import type { ReactNode } from "react";
import { Button } from "@/components/ui/button";
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
    <header className={ws.head}>
      <div className={ws.headInner}>
        <div>
          <h1>{title}</h1>
          <p className={ws.subtitle}>{subtitle}</p>
        </div>
        <div className={ws.actions}>{actions}</div>
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
    <div className={ws.cardTop}>
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
      className={`${ws.btn} ${variant === "primary" ? "primary" : variant === "danger" ? "danger" : variant === "ghost" ? "quiet" : ""} ${size === "sm" ? "small" : ""} ${className}`}
    />
  );
}
export function WorkspaceStatus({ status }: { status: string }) {
  return (
    <span className={`${ws.status} ${status}`}>
      {status.charAt(0) + status.slice(1).toLowerCase()}
    </span>
  );
}
export function WorkspaceStats({ action }: { action?: ReactNode }) {
  return (
    <div className={ws.stats} aria-label="Workspace counts unavailable">
      {["Documents", "Equipment", "Connections"].map((label) => (
        <div className={ws.stat} key={label}>
          <strong title="Count not provided by revision metadata">—</strong>
          <small>{label}</small>
        </div>
      ))}
      {action}
    </div>
  );
}
