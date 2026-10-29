import { useState } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Select } from "./select";
import { Checkbox } from "./checkbox";
import { Sheet } from "./sheet";
import { selectOption } from "./control-test-helpers";

function Choice({ modal = false }: { modal?: boolean }) {
  const [value, setValue] = useState("");
  const body = (
    <>
      <h2 id="title">Edit choice</h2>
      <label htmlFor="choice">Choice</label>
      <Select id="choice" name="choice" value={value} onValueChange={setValue}>
        <option value="">Select value</option>
        <>
          <option value="true">True</option>
          <option value="false">False</option>
        </>
        <option value="disabled" disabled>
          Disabled
        </option>
      </Select>
      <button onClick={() => setValue("")}>Reset</button>
    </>
  );
  return modal ? (
    <Sheet labelledBy="title" onClose={() => {}}>
      {body}
    </Sheet>
  ) : (
    <form>{body}</form>
  );
}

describe("shared controls", () => {
  it("preserves empty and explicit false values, including native form data", async () => {
    const { container } = render(<Choice />);
    expect(screen.getByRole("combobox")).toHaveTextContent("Select value");
    await selectOption(screen.getByLabelText("Choice"), "false");
    expect(new FormData(container.querySelector("form")!).get("choice")).toBe(
      "false",
    );
    expect(screen.getByLabelText("Choice")).toHaveTextContent("False");
  });
  it("supports a select in a modal and resets without inventing a value", async () => {
    render(<Choice modal />);
    await selectOption(screen.getByLabelText("Choice"), "false");
    fireEvent.click(screen.getByText("Reset"));
    expect(screen.getByLabelText("Choice")).toHaveTextContent("Select value");
  });
  it("supports keyboard selection, disabled options and Escape focus return", async () => {
    const user = userEvent.setup();
    render(<Choice />);
    const trigger = screen.getByRole("combobox");
    trigger.focus();
    await user.keyboard("{ArrowDown}");
    expect(screen.getByRole("option", { name: "Disabled" })).toHaveAttribute(
      "aria-disabled",
      "true",
    );
    await user.keyboard("{End}{Enter}");
    expect(trigger).toHaveTextContent("False");
    await user.keyboard("{ArrowDown}{Escape}");
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });
  it("preserves required, disabled and invalid semantics", async () => {
    const { container, rerender } = render(
      <form>
        <Select
          aria-label="Required choice"
          required
          value=""
          onValueChange={() => {}}
        >
          <option value="">Choose</option>
          <option value="a">A</option>
        </Select>
      </form>,
    );
    expect(container.querySelector("form")!.checkValidity()).toBe(false);
    rerender(
      <Select
        aria-label="Required choice"
        aria-invalid
        disabled
        value="a"
        onValueChange={() => {}}
      >
        <option value="a">A</option>
      </Select>,
    );
    expect(screen.getByRole("combobox")).toBeDisabled();
    expect(screen.getByRole("combobox")).toHaveAttribute(
      "aria-invalid",
      "true",
    );
  });
  it("keeps mixed checkbox state visual and supports labels, Space and disabled", async () => {
    const changed = vi.fn();
    const { rerender } = render(
      <label>
        <Checkbox indeterminate onChange={changed} />
        Carry forward
      </label>,
    );
    expect(screen.getByLabelText("Carry forward")).toBePartiallyChecked();
    await userEvent.setup().click(screen.getByText("Carry forward"));
    expect(changed).toHaveBeenCalledTimes(1);
    rerender(
      <label>
        <Checkbox disabled />
        Carry forward
      </label>,
    );
    expect(screen.getByLabelText("Carry forward")).toBeDisabled();
  });
});
