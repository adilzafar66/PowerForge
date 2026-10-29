import { fireEvent, screen, within } from "@testing-library/react";

/** Exercise the real portalled control instead of native select change events. */
export async function selectOption(control: HTMLElement, valueOrLabel: string) {
  fireEvent.keyDown(control, { key: "ArrowDown" });

  const listbox = screen.getByRole("listbox", { hidden: true });
  const options = within(listbox).getAllByRole("option", { hidden: true });
  const option = options.find(
    (item) =>
      item.getAttribute("data-value") === valueOrLabel ||
      item.textContent === valueOrLabel,
  );
  if (!option) throw new Error(`No option ${valueOrLabel}`);

  fireEvent.click(option);
}

export async function changeField(
  control: HTMLElement,
  init: { target: { value: string } },
) {
  if (control.getAttribute("role") === "combobox")
    await selectOption(control, init.target.value);
  else fireEvent.change(control, init);
}
