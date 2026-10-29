import {
  cloneElement,
  isValidElement,
  type ReactNode,
  type AriaAttributes,
} from "react";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

export function Field({
  id,
  label,
  required,
  children,
  className,
  hint,
  error,
}: {
  id?: string;
  label: string;
  required?: boolean;
  children: ReactNode;
  className?: string;
  hint?: ReactNode;
  error?: string;
}) {
  const describedBy = id
    ? [hint && `${id}-hint`, error && `${id}-error`].filter(Boolean).join(" ")
    : undefined;
  const control =
    id && isValidElement<AriaAttributes>(children)
      ? cloneElement(children, {
          "aria-describedby":
            [children.props["aria-describedby"], describedBy]
              .filter(Boolean)
              .join(" ") || undefined,
          "aria-invalid": error ? true : children.props["aria-invalid"],
        })
      : children;
  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      <Label htmlFor={id}>
        {label}
        {required && (
          <span aria-hidden className="ml-0.5 text-danger">
            *
          </span>
        )}
      </Label>
      {control}
      {hint && (
        <p
          id={id ? `${id}-hint` : undefined}
          className="text-[12px] text-muted"
        >
          {hint}
        </p>
      )}
      {error && (
        <p
          id={id ? `${id}-error` : undefined}
          role="alert"
          className="text-[12px] text-danger"
        >
          {error}
        </p>
      )}
    </div>
  );
}
