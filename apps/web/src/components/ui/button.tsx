import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-1.5 font-medium transition-all duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-1 disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-40 cursor-pointer select-none",
  {
    variants: {
      variant: {
        default:
          "bg-gradient-to-b from-[#2477e0] to-[#1a64c8] text-white shadow-[0_1px_3px_rgba(29,111,216,0.35),inset_0_1px_0_rgba(255,255,255,0.12)] hover:from-[#2070d4] hover:to-[#1759b8] active:from-[#1759b8] active:to-[#1452aa] active:shadow-none",
        primary:
          "bg-gradient-to-b from-[#2477e0] to-[#1a64c8] text-white shadow-[0_1px_3px_rgba(29,111,216,0.35),inset_0_1px_0_rgba(255,255,255,0.12)] hover:from-[#2070d4] hover:to-[#1759b8] active:from-[#1759b8] active:to-[#1452aa] active:shadow-none",
        secondary:
          "border border-slate-200 bg-white text-slate-700 shadow-[0_1px_2px_rgba(0,0,0,0.06)] hover:border-slate-300 hover:bg-slate-50 active:bg-slate-100",
        outline:
          "border border-slate-200 bg-white text-slate-700 shadow-[0_1px_2px_rgba(0,0,0,0.05)] hover:border-slate-300 hover:bg-slate-50 active:bg-slate-100",
        ghost: "text-slate-600 hover:bg-slate-100 hover:text-slate-900 active:bg-slate-200",
        danger:
          "bg-gradient-to-b from-red-500 to-red-600 text-white shadow-[0_1px_3px_rgba(239,68,68,0.3)] hover:from-red-600 hover:to-red-700 active:shadow-none",
      },
      size: {
        default: "rounded-lg px-4 py-[7px] text-[13.5px]",
        sm: "rounded-md px-2.5 py-[5px] text-[12.5px]",
        md: "rounded-lg px-4 py-[7px] text-[13.5px]",
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
    asChild?: boolean;
  };

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return <Comp className={cn(buttonVariants({ variant, size, className }))} ref={ref} {...props} />;
  },
);
Button.displayName = "Button";

export { Button, buttonVariants };
