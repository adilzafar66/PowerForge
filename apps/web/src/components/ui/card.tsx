import * as React from "react";

import { cn } from "@/lib/utils";

type CardProps = React.HTMLAttributes<HTMLElement> & {
  as?: "div" | "article" | "section";
  presentation?: "default" | "workspace";
  spacing?: "none" | "body" | "rail" | "work";
};
function Card({
  as: Element = "div",
  presentation = "default",
  spacing = "none",
  className,
  ...props
}: CardProps) {
  return (
    <Element
      className={cn(
        "rounded-xl border border-border bg-white text-slate-900",
        presentation === "workspace" &&
          "bg-panel border border-border rounded-[var(--pf-radius-lg)] overflow-hidden min-w-0",
        spacing === "body" && "p-6 max-[530px]:p-[18px]",
        spacing === "rail" && "p-5",
        spacing === "work" && "py-[22px] px-6",
        className,
      )}
      {...props}
    />
  );
}

function CardHeader({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cn("flex flex-col gap-1.5 p-5", className)} {...props} />
  );
}

function CardTitle({
  className,
  ...props
}: React.HTMLAttributes<HTMLHeadingElement>) {
  return (
    <h3
      className={cn(
        "text-[15px] font-semibold leading-none tracking-tight",
        className,
      )}
      {...props}
    />
  );
}

function CardDescription({
  className,
  ...props
}: React.HTMLAttributes<HTMLParagraphElement>) {
  return (
    <p className={cn("text-[13px] text-slate-500", className)} {...props} />
  );
}

function CardContent({
  presentation = "default",
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement> & {
  presentation?: "default" | "workspace";
}) {
  return (
    <div
      className={cn(
        presentation === "workspace" ? "p-6 max-[530px]:p-[18px]" : "p-5 pt-0",
        className,
      )}
      {...props}
    />
  );
}

export { Card, CardContent, CardDescription, CardHeader, CardTitle };
