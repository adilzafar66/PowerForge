import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Button } from "./button";
import { Field } from "./field";
import { Input } from "./input";
import { Sheet } from "./sheet";
import { SegmentedControl } from "./segmented-control";

describe("workspace presentation contracts", () => {
  it("preserves field errors, input refs, and pending button semantics", () => {
    const ref = { current: null as HTMLInputElement | null };
    render(
      <>
        <Field
          id="name"
          label="Name"
          presentation="workspace"
          hint="Project name"
          error="Required"
        >
          <Input id="name" ref={ref} presentation="workspace" />
        </Field>
        <Button presentation="workspace" pending>
          Save
        </Button>
      </>,
    );
    expect(ref.current).toBe(screen.getByRole("textbox", { name: "Name" }));
    expect(ref.current).toHaveAttribute(
      "aria-describedby",
      "name-hint name-error",
    );
    expect(ref.current).toHaveAttribute("aria-invalid", "true");
    expect(ref.current).not.toHaveAttribute("presentation");
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Save" })).toHaveAttribute(
      "aria-busy",
      "true",
    );
  });
  it("keeps portalled sheet labelling and cancellation independent of its title", async () => {
    const close = vi.fn();
    render(
      <Sheet
        presentation="workspace-project"
        labelledBy="custom-title"
        onClose={close}
      >
        <h2 id="custom-title">Custom title</h2>
      </Sheet>,
    );
    expect(
      screen.getByRole("dialog", { name: "Custom title" }),
    ).not.toHaveAttribute("presentation");
    await userEvent.setup().keyboard("{Escape}");
    expect(close).toHaveBeenCalledOnce();
  });
  it.each(["projects", "revisions"] as const)(
    "retains keyboard selection and counts for %s",
    async (presentation) => {
      const change = vi.fn();
      render(
        <SegmentedControl
          presentation={presentation}
          label="Statuses"
          value="all"
          onChange={change}
          options={[
            { value: "all", label: "All", count: 3 },
            { value: "draft", label: "Draft", count: 1 },
          ]}
        />,
      );
      const draft = screen.getByRole("button", { name: "Draft 1" });
      draft.focus();
      await userEvent.setup().keyboard("{Enter}");
      expect(change).toHaveBeenCalledWith("draft");
      expect(screen.getByRole("button", { name: "All 3" })).toHaveAttribute(
        "aria-pressed",
        "true",
      );
    },
  );
});
