"use client";

import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useRef,
  type InputHTMLAttributes,
} from "react";
import { cn } from "@/lib/utils";

/** Mixed is visual only; the native checked boolean remains the submitted value. */
export const Checkbox = forwardRef<
  HTMLInputElement,
  Omit<InputHTMLAttributes<HTMLInputElement>, "type"> & {
    indeterminate?: boolean;
  }
>(function Checkbox(
  { indeterminate = false, className, ...props },
  forwardedRef,
) {
  const ref = useRef<HTMLInputElement>(null);
  useImperativeHandle(forwardedRef, () => ref.current!);
  useEffect(() => {
    if (ref.current) ref.current.indeterminate = indeterminate;
  }, [indeterminate]);
  return (
    <input
      {...props}
      ref={ref}
      type="checkbox"
      className={cn("pf-checkbox", className)}
    />
  );
});
