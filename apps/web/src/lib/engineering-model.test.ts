import { afterEach, describe, expect, it, vi } from "vitest";
import * as model from "./engineering-model";

describe("engineering model API", () => {
  afterEach(() => vi.restoreAllMocks());
  it("uses the registry and scoped list query, preserving decimal/boolean/state-only bodies", async () => {
    const fetch = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue({
        ok: true,
        json: async () => ({ items: [] }),
      } as Response);
    await model.getEngineeringRegistry();
    expect(String(fetch.mock.calls[0][0])).toContain(
      "/api/engineering-model/registry",
    );
    await model.listEquipment("p", "r", {
      search: "main & spare",
      equipment_type: "FROM_REGISTRY",
      lifecycle_status: "ALL",
    });
    expect(String(fetch.mock.calls[1][0])).toContain(
      "equipment?search=main+%26+spare&equipment_type=FROM_REGISTRY&lifecycle_status=ALL",
    );
    const bodies: model.AttributeInput[] = [
      {
        information_state: "PRESENT",
        value: "0.1234567890123456789012345678901234",
        unit: "V",
      },
      { information_state: "PRESENT", value: false },
      { information_state: "MISSING" },
    ];
    for (const body of bodies) {
      await model.setAttribute("p", "r", "e", "rating", body);
      expect(fetch.mock.lastCall?.[1]).toMatchObject({
        method: "PUT",
        body: JSON.stringify(body),
      });
    }
  });
  it("routes manual equipment, node and connection operations without invented metadata", async () => {
    const fetch = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue({
        ok: true,
        json: async () => ({ items: [] }),
      } as Response);
    const calls: [() => Promise<unknown>, string, string, object?][] = [
      [
        () =>
          model.createEquipment("p", "r", {
            equipment_type: "TYPE",
            tag: "DUP",
          }),
        "equipment",
        "POST",
        { equipment_type: "TYPE", tag: "DUP" },
      ],
      [
        () => model.updateEquipment("p", "r", "e", { tag: null }),
        "equipment/e",
        "PATCH",
        { tag: null },
      ],
      [
        () => model.removeEquipment("p", "r", "e"),
        "equipment/e/remove",
        "POST",
      ],
      [
        () => model.restoreEquipment("p", "r", "e"),
        "equipment/e/restore",
        "POST",
      ],
      [
        () => model.createTerminal("p", "r", "e", { terminal_key: "A" }),
        "nodes",
        "POST",
        { terminal_key: "A", kind: "EQUIPMENT_TERMINAL", equipment_id: "e" },
      ],
      [
        () => model.createElectricalNode("p", "r", null),
        "nodes",
        "POST",
        { kind: "ELECTRICAL_NODE", label: null },
      ],
      [
        () => model.updateNode("p", "r", "n", { label: null }),
        "nodes/n",
        "PATCH",
        { label: null },
      ],
      [() => model.removeNode("p", "r", "n"), "nodes/n/remove", "POST"],
      [() => model.restoreNode("p", "r", "n"), "nodes/n/restore", "POST"],
      [
        () =>
          model.createConnection("p", "r", {
            from_node_id: "a",
            to_node_id: "b",
            nominal_voltage: "600",
          }),
        "connections",
        "POST",
        { from_node_id: "a", to_node_id: "b", nominal_voltage: "600" },
      ],
      [
        () =>
          model.updateConnection("p", "r", "c", {
            nominal_voltage: null,
            nominal_voltage_unit: null,
          }),
        "connections/c",
        "PATCH",
        { nominal_voltage: null, nominal_voltage_unit: null },
      ],
      [
        () => model.removeConnection("p", "r", "c"),
        "connections/c/remove",
        "POST",
      ],
      [
        () => model.restoreConnection("p", "r", "c"),
        "connections/c/restore",
        "POST",
      ],
    ];
    for (const [run, path, method, body] of calls) {
      await run();
      expect(String(fetch.mock.lastCall?.[0])).toContain(
        `/api/projects/p/revisions/r/${path}`,
      );
      expect(fetch.mock.lastCall?.[1]).toMatchObject({ method });
      expect(fetch.mock.lastCall?.[1]?.body).toBe(
        body ? JSON.stringify(body) : undefined,
      );
    }
  });
  it("blocks all empty PATCH calls before fetch", async () => {
    const fetch = vi.spyOn(globalThis, "fetch");
    await expect(model.updateEquipment("p", "r", "e", {})).rejects.toThrow(
      "No changes",
    );
    await expect(model.updateNode("p", "r", "n", {})).rejects.toThrow(
      "No changes",
    );
    await expect(model.updateConnection("p", "r", "c", {})).rejects.toThrow(
      "No changes",
    );
    expect(fetch).not.toHaveBeenCalled();
  });
});
