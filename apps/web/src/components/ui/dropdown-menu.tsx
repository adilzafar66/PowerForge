"use client";

import * as Menu from "@radix-ui/react-dropdown-menu";
import { ChevronDown, MoreVertical } from "lucide-react";
import { Fragment, type ReactNode } from "react";
import { cn } from "@/lib/utils";

export type DropdownMenuItem = {
  id: string;
  label: ReactNode;
  onSelect: () => void;
  disabled?: boolean;
  destructive?: boolean;
  separatorBefore?: boolean;
};

export function DropdownMenu({
  items,
  label = "Open menu",
  align = "right",
  disabled = false,
  className,
  triggerClassName,
  triggerLabel,
}: {
  items: DropdownMenuItem[];
  label?: string;
  align?: "left" | "right";
  disabled?: boolean;
  className?: string;
  triggerClassName?: string;
  triggerLabel?: string;
}) {
  if (!items.length) return null;
  return (
    <span className={cn("inline-flex", className)}>
      <Menu.Root modal={false}>
        <Menu.Trigger
          disabled={disabled}
          aria-label={triggerLabel ? undefined : label}
          className={cn(
            "inline-flex min-h-8 min-w-8 cursor-pointer items-center justify-center gap-1.5 rounded-lg text-muted transition-colors hover:bg-soft focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus disabled:cursor-not-allowed disabled:opacity-40",
            triggerLabel &&
              "min-h-10 border border-border bg-panel px-3 text-[13px] font-medium",
            triggerClassName,
          )}
        >
          {triggerLabel ? (
            <>
              {triggerLabel}
              <ChevronDown aria-hidden className="h-3.5 w-3.5" />
            </>
          ) : (
            <MoreVertical aria-hidden className="h-5 w-5" />
          )}
        </Menu.Trigger>
        <Menu.Portal>
          <Menu.Content
            aria-label={label}
            align={align === "right" ? "end" : "start"}
            sideOffset={6}
            collisionPadding={12}
            className="z-[80] min-w-[180px] max-w-[calc(100vw-24px)] rounded-[10px] border border-border bg-panel p-1 shadow-lg"
          >
            {items.map((item) => (
              <Fragment key={item.id}>
                {item.separatorBefore && (
                  <Menu.Separator className="my-1 border-t border-border" />
                )}
                <Menu.Item
                  disabled={item.disabled}
                  onSelect={item.onSelect}
                  className={cn(
                    "flex min-h-9 cursor-pointer items-center rounded-md px-3 py-2 text-[13px] font-medium outline-none transition-colors data-[disabled]:pointer-events-none data-[disabled]:opacity-40",
                    item.destructive
                      ? "text-danger data-[highlighted]:bg-danger-tint"
                      : "text-ink data-[highlighted]:bg-soft",
                  )}
                >
                  {item.label}
                </Menu.Item>
              </Fragment>
            ))}
          </Menu.Content>
        </Menu.Portal>
      </Menu.Root>
    </span>
  );
}
