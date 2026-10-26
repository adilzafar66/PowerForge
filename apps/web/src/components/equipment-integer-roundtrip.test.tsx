/** @vitest-environment jsdom */
import React from "react";
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { EquipmentAttributesPanel } from "@/components/equipment-attributes-panel";
import { ModelContext } from "@/components/model-shared";
import {
  attributes,
  equipment,
  registry,
} from "@/components/model-test-fixtures";

afterEach(() => vi.restoreAllMocks());

it.each(["3", "9007199254740993"])(
  "decodes, displays and resubmits the canonical INTEGER string %s exactly",
  async (value) => {
    const row = {
      ...attributes.find((a) => a.attribute_key === "count")!,
      information_state: "PRESENT" as const,
      integer_value: value,
    };
    // Exercise the real request helper and JSON decoder, not a mocked model API.
    const fetch = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            items: attributes.map((a) => (a.id === row.id ? row : a)),
          }),
        ),
      )
      .mockResolvedValueOnce(new Response(JSON.stringify(row)));
    render(
      <ModelContext.Provider
        value={{
          projectId: "p",
          revisionId: "r",
          registry,
          writable: true,
          version: 0,
          changed: vi.fn(),
          failed: vi.fn(),
        }}
      >
        <EquipmentAttributesPanel row={equipment} />
      </ModelContext.Provider>,
    );
    const form = within(await screen.findByRole("form", { name: "Count" }));
    const input = form.getByLabelText("Value");
    expect(input).toHaveValue(value);
    expect(form.getByText("Save attribute")).toBeDisabled();
    // A whitespace edit exercises trimming/resubmission without changing the integer.
    fireEvent.change(input, { target: { value: `${value} ` } });
    fireEvent.click(form.getByText("Save attribute"));
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
    expect(fetch.mock.calls[1][1]?.method).toBe("PUT");
    expect(JSON.parse(fetch.mock.calls[1][1]?.body as string)).toEqual({
      information_state: "PRESENT",
      value,
    });
    await form.findByText("Saved.");
    expect(input).toHaveValue(value);
  },
);
