import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-1.5 font-medium transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-1 disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-40 cursor-pointer select-none",
  {
    variants: {
      variant: {
        default:
          "bg-accent text-white hover:bg-accent-hover active:bg-accent-hover",
        primary:
          "bg-accent text-white hover:bg-accent-hover active:bg-accent-hover",
        secondary:
          "border border-slate-200 bg-white text-slate-700 hover:border-slate-300 hover:bg-slate-50 active:bg-slate-100",
        outline:
          "border border-slate-200 bg-white text-slate-700 hover:border-slate-300 hover:bg-slate-50 active:bg-slate-100",
        ghost:
          "text-slate-600 hover:bg-slate-100 hover:text-slate-900 active:bg-slate-200",
        danger: "bg-danger text-white hover:brightness-90",
      },
      size: {
        default: "min-h-10 rounded-lg px-4 py-[7px] text-[13.5px]",
        sm: "min-h-8 rounded-md px-2.5 py-[5px] text-[12.5px]",
        md: "min-h-10 rounded-lg px-4 py-[7px] text-[13.5px]",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  },
);

export type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> &
  VariantProps<typeof buttonVariants> & {
    presentation?: "default" | "workspace" | "workspace-dialog";
    asChild?: boolean;
    pending?: boolean;
  };

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  (
    {
      className,
      presentation = "default",
      variant,
      size,
      asChild = false,
      pending = false,
      disabled,
      ...props
    },
    ref,
  ) => {
    const Comp = asChild ? Slot : "button";
    const resolvedVariant =
      variant ?? (presentation === "workspace" ? "outline" : "default");
    return (
      <Comp
        className={cn(
          buttonVariants({ variant: resolvedVariant, size }),
          presentation === "workspace" && [
            "border border-border bg-panel text-ink rounded-[var(--pf-radius-control)] py-0 px-[14px] min-h-[var(--pf-control-height-action)] h-auto inline-flex items-center justify-center gap-2 font-medium text-workspace-button shadow-none [transition:background_var(--pf-transition-fast)_ease,_transform_var(--pf-transition-fast)_ease,_border-color_var(--pf-transition-fast)_ease] whitespace-nowrap hover:border-border hover:bg-soft hover:text-ink active:[transform:translateY(1px)]",
            "[&>svg]:size-4",
            variant === "primary" &&
              "bg-accent border-[var(--pf-action)] text-[var(--pf-surface)] hover:border-accent hover:text-white hover:bg-accent-hover active:bg-accent-hover",
            variant === "danger" &&
              "text-[var(--pf-action-destructive)] border-[var(--pf-action-destructive-border)] hover:bg-[var(--pf-action-destructive-hover)] hover:border-[var(--pf-action-destructive-border)] hover:text-[var(--pf-action-destructive)]",
            variant === "ghost" &&
              "border-transparent text-muted hover:border-transparent hover:text-muted",
            size === "sm" &&
              "min-h-[var(--pf-control-height-compact)] py-0 px-[10px] text-workspace-button-small",
          ],
          presentation === "workspace-dialog" &&
            "min-h-[var(--pf-control-height-action)] rounded-[var(--pf-radius-control)] text-workspace-button font-medium",
          className,
        )}
        ref={ref}
        disabled={disabled || pending}
        aria-busy={pending || undefined}
        {...props}
      />
    );
  },
);
Button.displayName = "Button";

export { Button, buttonVariants };
