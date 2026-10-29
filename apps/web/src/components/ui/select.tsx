"use client";

import * as Primitive from "@radix-ui/react-select";
import { Check, ChevronDown, ChevronUp } from "lucide-react";
import {
  Children,
  Fragment,
  isValidElement,
  type ReactNode,
  type ReactElement,
  type AriaAttributes,
} from "react";
import { cn } from "@/lib/utils";
import { fieldClassName } from "@/components/ui/input";

export type SelectProps = AriaAttributes & {
  id?: string;
  name?: string;
  value: string;
  onValueChange: (value: string) => void;
  children: ReactNode;
  disabled?: boolean;
  required?: boolean;
  className?: string;
  size?: "sm" | "default";
};

/** Option children keep existing enum/null definitions at their domain call sites. */
export function Select({
  id,
  name,
  value,
  onValueChange,
  children,
  disabled,
  required,
  className,
  size = "default",
  ...aria
}: SelectProps) {
  const options = optionElements(children);
  const emptyLabel = options.find((option) => option.props.value === "")?.props
    .children;
  return (
    <>
      <Primitive.Root
        name={name}
        value={value}
        onValueChange={onValueChange}
        disabled={disabled}
        required={required}
      >
        <Primitive.Trigger
          id={id}
          {...aria}
          className={cn(
            fieldClassName,
            "items-center justify-between gap-2 text-left",
            size === "sm" ? "min-h-8 py-1 text-[12px]" : "min-h-10",
            className,
          )}
        >
          <Primitive.Value placeholder={emptyLabel ?? "Select value"} />
          <Primitive.Icon asChild>
            <ChevronDown aria-hidden className="h-4 w-4 shrink-0 text-muted" />
          </Primitive.Icon>
        </Primitive.Trigger>
        <Primitive.Portal>
          <Primitive.Content
            position="popper"
            sideOffset={5}
            collisionPadding={12}
            className="z-[80] max-h-[var(--radix-select-content-available-height)] min-w-[var(--radix-select-trigger-width)] max-w-[calc(100vw-24px)] overflow-hidden rounded-[10px] border border-border bg-panel p-1 shadow-lg"
          >
            <Primitive.ScrollUpButton className="flex justify-center py-1">
              <ChevronUp className="h-4 w-4" />
            </Primitive.ScrollUpButton>
            <Primitive.Viewport>
              {options.map((option) => (
                <SelectItem
                  key={option.props.value}
                  value={String(option.props.value)}
                  rawValue={String(option.props.value)}
                  disabled={option.props.disabled}
                >
                  {option.props.children}
                </SelectItem>
              ))}
            </Primitive.Viewport>
            <Primitive.ScrollDownButton className="flex justify-center py-1">
              <ChevronDown className="h-4 w-4" />
            </Primitive.ScrollDownButton>
          </Primitive.Content>
        </Primitive.Portal>
      </Primitive.Root>
    </>
  );
}

export function SelectItem({
  children,
  rawValue,
  ...props
}: Primitive.SelectItemProps & { rawValue?: string }) {
  return (
    <Primitive.Item
      {...props}
      data-value={rawValue}
      className={cn(
        "pf-select-option relative flex min-h-9 cursor-default items-center rounded-md py-2 pr-8 pl-3 text-[13px] outline-none data-[disabled]:pointer-events-none data-[disabled]:opacity-50",
        props.className,
      )}
    >
      <Primitive.ItemText>{children}</Primitive.ItemText>
      <Primitive.ItemIndicator className="absolute right-2">
        <Check aria-hidden className="h-4 w-4" />
      </Primitive.ItemIndicator>
    </Primitive.Item>
  );
}

type OptionProps = { value: string; children: ReactNode; disabled?: boolean };
function optionElements(children: ReactNode): ReactElement<OptionProps>[] {
  return Children.toArray(children).flatMap((child) => {
    if (!isValidElement<OptionProps>(child)) return [];
    if (child.type === Fragment) return optionElements(child.props.children);
    return child.type === "option" ? [child] : [];
  });
}
