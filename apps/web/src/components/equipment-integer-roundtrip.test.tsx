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
import { EquipmentDetailDrawer } from "@/components/equipment-detail-drawer";
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
            equipment,
            terminals: [],
            attributes: attributes.map((a) => (a.id === row.id ? row : a)),
          }),
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            equipment,
            terminals: [],
            attributes: attributes.map((a) => (a.id === row.id ? row : a)),
          }),
        ),
      );
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
        <EquipmentDetailDrawer id={equipment.id} onClose={vi.fn()} />
      </ModelContext.Provider>,
    );
    fireEvent.click(await screen.findByText("Attributes"));
    const form = within(await screen.findByRole("group", { name: "Count" }));
    const input = form.getByLabelText("Value");
    expect(input).toHaveValue(value);
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
    // A whitespace edit exercises trimming/resubmission without changing the integer.
    fireEvent.change(input, { target: { value: `${value} ` } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
    expect(fetch.mock.calls[1][1]?.method).toBe("PATCH");
    expect(JSON.parse(fetch.mock.calls[1][1]?.body as string)).toEqual({
      attributes: { count: { information_state: "PRESENT", value } },
    });
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Save" })).toBeDisabled(),
    );
    expect(input).toHaveValue(value);
  },
);
