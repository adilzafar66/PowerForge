/** @vitest-environment jsdom */
import React from "react";
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  ModelContext,
  type ModelContextValue,
} from "@/components/model-shared";
import { EquipmentGeneralPanel } from "@/components/equipment-general-panel";
import { EquipmentAttributesPanel } from "@/components/equipment-attributes-panel";
import { EquipmentTerminalsPanel } from "@/components/equipment-terminals-panel";
import { ConnectionEditorSheet } from "@/components/connection-editor-sheet";
import { TopologyWorkspace } from "@/components/topology-workspace";
import {
  attributes,
  connection,
  definitions,
  equipment,
  junction,
  registry,
  terminal,
} from "@/components/model-test-fixtures";
import * as api from "@/lib/engineering-model";
vi.mock("@/lib/engineering-model", async (original) => ({
  ...(await original<typeof api>()),
  createEquipment: vi.fn(),
  updateEquipment: vi.fn(),
  listAttributes: vi.fn(),
  setAttribute: vi.fn(),
  listNodes: vi.fn(),
  createTerminal: vi.fn(),
  updateNode: vi.fn(),
  removeNode: vi.fn(),
  restoreNode: vi.fn(),
  createElectricalNode: vi.fn(),
  listConnections: vi.fn(),
  listEquipment: vi.fn(),
  createConnection: vi.fn(),
  updateConnection: vi.fn(),
  removeConnection: vi.fn(),
  restoreConnection: vi.fn(),
}));
let context: ModelContextValue;
function mount(child: React.ReactNode) {
  return render(
    <ModelContext.Provider value={context}>{child}</ModelContext.Provider>,
  );
}
beforeEach(() => {
  vi.resetAllMocks();
  context = {
    projectId: "p",
    revisionId: "r",
    registry,
    writable: true,
    version: 0,
    changed: vi.fn(),
    failed: vi.fn(),
  };
  vi.mocked(api.listAttributes).mockResolvedValue(attributes);
  vi.mocked(api.listNodes).mockResolvedValue([terminal, junction]);
  vi.mocked(api.listConnections).mockResolvedValue([
    connection,
    { ...connection, id: "c2" },
  ]);
  vi.mocked(api.listEquipment).mockResolvedValue([equipment]);
  vi.mocked(api.updateEquipment).mockResolvedValue(equipment);
  vi.mocked(api.createEquipment).mockResolvedValue(equipment);
});
describe("equipment editors", () => {
  it("sends only changed text, clears with null and blocks empty saves", async () => {
    mount(<EquipmentGeneralPanel row={equipment} onSaved={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Save general" })).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Tag"), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Save general" }));
    await waitFor(() =>
      expect(api.updateEquipment).toHaveBeenCalledWith("p", "r", "e1", {
        tag: null,
      }),
    );
  });
  it("creates with registry keys and allows a duplicate-looking tag", async () => {
    mount(<EquipmentGeneralPanel onSaved={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Tag"), {
      target: { value: "SWGR-1" },
    });
    fireEvent.click(screen.getByText("Create Equipment"));
    await waitFor(() =>
      expect(api.createEquipment).toHaveBeenCalledWith("p", "r", {
        equipment_type: "TEST_DEVICE",
        tag: "SWGR-1",
        name: "",
        description: "",
      }),
    );
  });
  it("preserves draft on type conflict and requests canonical refresh", async () => {
    vi.mocked(api.updateEquipment).mockRejectedValue(
      Object.assign(new Error("Meaningful attributes prevent type change"), {
        status: 409,
        apiError: {
          code: "equipment_type_change_conflict",
          detail: "Meaningful attributes prevent type change",
        },
      }),
    );
    mount(<EquipmentGeneralPanel row={equipment} onSaved={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Equipment Type"), {
      target: { value: "ALTERNATE" },
    });
    fireEvent.click(screen.getByText("Save general"));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Meaningful attributes",
    );
    expect(screen.getByLabelText("Equipment Type")).toHaveValue("ALTERNATE");
    expect(context.failed).toHaveBeenCalled();
  });
  it("renders registry order and independent badges, preserves NUMBER and INTEGER strings", async () => {
    mount(<EquipmentAttributesPanel row={equipment} />);
    await screen.findByRole("form", { name: "Rated voltage" });
    expect(
      screen.getAllByRole("form").map((f) => f.getAttribute("aria-label")),
    ).toEqual(definitions.map((a) => a.display_name));
    const voltage = within(screen.getByRole("form", { name: "Rated voltage" }));
    expect(voltage.getByText("Required")).toBeInTheDocument();
    expect(voltage.queryByText("Critical")).not.toBeInTheDocument();
    expect(
      within(screen.getByRole("form", { name: "Count" })).getByText("Critical"),
    ).toBeInTheDocument();
    expect(
      within(screen.getByRole("form", { name: "Operating mode" })).getByText(
        "Conditional",
      ),
    ).toBeInTheDocument();
    const precise = "0.1234567890123456789012345678901234";
    vi.mocked(api.setAttribute).mockResolvedValue({
      ...attributes[0],
      information_state: "PRESENT",
      numeric_value: precise,
    });
    fireEvent.change(voltage.getByLabelText("Information state"), {
      target: { value: "PRESENT" },
    });
    fireEvent.change(voltage.getByLabelText("Value"), {
      target: { value: precise },
    });
    fireEvent.change(voltage.getByLabelText("Input unit"), {
      target: { value: "V" },
    });
    fireEvent.click(voltage.getByText("Save attribute"));
    await waitFor(() =>
      expect(api.setAttribute).toHaveBeenCalledWith("p", "r", "e1", "voltage", {
        information_state: "PRESENT",
        value: precise,
        unit: "V",
      }),
    );
    const count = within(screen.getByRole("form", { name: "Count" }));
    fireEvent.change(count.getByLabelText("Information state"), {
      target: { value: "PRESENT" },
    });
    fireEvent.change(count.getByLabelText("Value"), {
      target: { value: "9007199254740993" },
    });
    fireEvent.click(count.getByText("Save attribute"));
    await waitFor(() =>
      expect(api.setAttribute).toHaveBeenCalledWith("p", "r", "e1", "count", {
        information_state: "PRESENT",
        value: "9007199254740993",
      }),
    );
  });
  it.each(["UNKNOWN", "MISSING", "NOT_APPLICABLE"] as const)(
    "saves %s without stale value/unit",
    async (state) => {
      vi.mocked(api.listAttributes).mockResolvedValue([
        {
          ...attributes[0],
          information_state: "PRESENT",
          numeric_value: "600",
        },
        ...attributes.slice(1),
      ]);
      vi.mocked(api.setAttribute).mockResolvedValue({
        ...attributes[0],
        information_state: state,
      });
      mount(<EquipmentAttributesPanel row={equipment} />);
      const form = within(
        await screen.findByRole("form", { name: "Rated voltage" }),
      );
      fireEvent.change(form.getByLabelText("Information state"), {
        target: { value: state },
      });
      expect(form.queryByLabelText("Value")).not.toBeInTheDocument();
      fireEvent.click(form.getByText("Save attribute"));
      await waitFor(() =>
        expect(api.setAttribute).toHaveBeenCalledWith(
          "p",
          "r",
          "e1",
          "voltage",
          { information_state: state },
        ),
      );
    },
  );
  it("uses registry enum choices, actual booleans and unmodified text", async () => {
    mount(<EquipmentAttributesPanel row={equipment} />);
    await screen.findByRole("form", { name: "Enabled" });
    for (const [label, key, value] of [
      ["Operating mode", "mode", "CHOICE_B"],
      ["Enabled", "enabled", "false"],
      ["Nameplate note", "note", "Original text"],
    ]) {
      const form = within(screen.getByRole("form", { name: label }));
      vi.mocked(api.setAttribute).mockResolvedValue({
        ...attributes.find((a) => a.attribute_key === key)!,
        information_state: "PRESENT",
      });
      fireEvent.change(form.getByLabelText("Information state"), {
        target: { value: "PRESENT" },
      });
      fireEvent.change(form.getByLabelText("Value"), { target: { value } });
      fireEvent.click(form.getByText("Save attribute"));
      await waitFor(() =>
        expect(api.setAttribute).toHaveBeenCalledWith("p", "r", "e1", key, {
          information_state: "PRESENT",
          value: key === "enabled" ? false : value,
        }),
      );
    }
  });
  it("preserves row draft and displays 422 errors", async () => {
    vi.mocked(api.setAttribute).mockRejectedValue(new Error("Invalid value"));
    mount(<EquipmentAttributesPanel row={equipment} />);
    const form = within(await screen.findByRole("form", { name: "Count" }));
    fireEvent.change(form.getByLabelText("Information state"), {
      target: { value: "PRESENT" },
    });
    fireEvent.change(form.getByLabelText("Value"), {
      target: { value: "1.5" },
    });
    fireEvent.click(form.getByText("Save attribute"));
    await form.findByText("Invalid value");
    expect(form.getByLabelText("Value")).toHaveValue("1.5");
  });
});
describe("terminals and topology", () => {
  it("filters terminals by Equipment, adds, edits, warns on remove, and restores", async () => {
    vi.mocked(api.listNodes).mockResolvedValue([
      terminal,
      {
        ...terminal,
        id: "other",
        equipment_id: "other",
        terminal_key: "OTHER",
      },
    ]);
    const view = mount(<EquipmentTerminalsPanel row={equipment} />);
    await screen.findByText("LINE · Active");
    expect(screen.queryByText(/OTHER/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByText("Add Terminal"));
    fireEvent.change(screen.getByLabelText(/Terminal key/), {
      target: { value: "LOAD" },
    });
    fireEvent.click(screen.getByText("Create terminal"));
    await waitFor(() =>
      expect(api.createTerminal).toHaveBeenCalledWith("p", "r", "e1", {
        terminal_key: "LOAD",
        label: null,
      }),
    );
    fireEvent.click(screen.getByText("Edit terminal"));
    expect(screen.getByText("Save node")).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Label"), {
      target: { value: "Input" },
    });
    fireEvent.click(screen.getByText("Save node"));
    await waitFor(() =>
      expect(api.updateNode).toHaveBeenCalledWith("p", "r", "terminal1", {
        label: "Input",
      }),
    );
    fireEvent.click(screen.getByText("Remove terminal"));
    expect(screen.getByRole("dialog")).toHaveTextContent(
      "active connections incident",
    );
    fireEvent.click(
      within(screen.getByRole("dialog")).getByText("Remove terminal"),
    );
    await waitFor(() => expect(api.removeNode).toHaveBeenCalled());
    view.unmount();
    vi.mocked(api.listNodes).mockResolvedValue([
      { ...terminal, lifecycle_status: "REMOVED" },
    ]);
    mount(<EquipmentTerminalsPanel row={equipment} />);
    fireEvent.click(await screen.findByText("Restore terminal"));
    await waitFor(() => expect(api.restoreNode).toHaveBeenCalled());
  });
  it("labels nodes, keeps parallel edges and refreshes connections after node removal", async () => {
    const view = mount(<TopologyWorkspace />);
    await screen.findAllByText("Electrical node · junction");
    expect(screen.getAllByText("SWGR-1 · LINE").length).toBe(3);
    expect(screen.getAllByText("Edit connection")).toHaveLength(2);
    fireEvent.click(screen.getByText("Add Electrical Node"));
    fireEvent.change(screen.getByLabelText("Label"), {
      target: { value: "Junction" },
    });
    fireEvent.click(screen.getByText("Create electrical node"));
    await waitFor(() =>
      expect(api.createElectricalNode).toHaveBeenCalledWith(
        "p",
        "r",
        "Junction",
      ),
    );
    fireEvent.click(screen.getByText("Remove node"));
    fireEvent.click(
      within(screen.getByRole("dialog")).getByText("Remove node"),
    );
    await waitFor(() => expect(context.changed).toHaveBeenCalled());
    view.rerender(
      <ModelContext.Provider value={{ ...context, version: 1 }}>
        <TopologyWorkspace />
      </ModelContext.Provider>,
    );
    await waitFor(() => expect(api.listConnections).toHaveBeenCalledTimes(2));
  });
  it("edits and restores electrical nodes, and removes/restores connections only with active endpoints", async () => {
    const view = mount(<TopologyWorkspace />);
    fireEvent.click(await screen.findByText("Edit node"));
    fireEvent.change(screen.getByLabelText("Label"), {
      target: { value: "Updated junction" },
    });
    fireEvent.click(screen.getByText("Save node"));
    await waitFor(() =>
      expect(api.updateNode).toHaveBeenCalledWith("p", "r", "junction1", {
        label: "Updated junction",
      }),
    );
    fireEvent.click(screen.getAllByText("Remove connection")[0]);
    await waitFor(() =>
      expect(api.removeConnection).toHaveBeenCalledWith("p", "r", "c1"),
    );
    vi.mocked(api.listNodes).mockResolvedValue([
      terminal,
      { ...junction, lifecycle_status: "REMOVED" },
    ]);
    vi.mocked(api.listConnections).mockResolvedValue([
      { ...connection, lifecycle_status: "REMOVED" },
    ]);
    view.rerender(
      <ModelContext.Provider value={{ ...context, version: 1 }}>
        <TopologyWorkspace />
      </ModelContext.Provider>,
    );
    fireEvent.click(
      within(screen.getByRole("group", { name: "Lifecycle" })).getByText(
        "Removed",
      ),
    );
    const restore = await screen.findByText("Restore connection");
    expect(restore).toBeDisabled();
    fireEvent.click(screen.getByText("Restore node"));
    await waitFor(() =>
      expect(api.restoreNode).toHaveBeenCalledWith("p", "r", "junction1"),
    );
    vi.mocked(api.listNodes).mockResolvedValue([terminal, junction]);
    view.rerender(
      <ModelContext.Provider value={{ ...context, version: 2 }}>
        <TopologyWorkspace />
      </ModelContext.Provider>,
    );
    await waitFor(() =>
      expect(screen.getByText("Restore connection")).toBeEnabled(),
    );
    fireEvent.click(screen.getByText("Restore connection"));
    await waitFor(() =>
      expect(api.restoreConnection).toHaveBeenCalledWith("p", "r", "c1"),
    );
  });
  it("creates connection with human endpoints and registry units, preserving voltage strings", async () => {
    mount(
      <ConnectionEditorSheet
        nodes={[terminal, junction]}
        labels={api.nodeLabels([terminal, junction], [equipment], registry)}
        onClose={vi.fn()}
      />,
    );
    fireEvent.change(screen.getByLabelText("From Node"), {
      target: { value: terminal.id },
    });
    fireEvent.change(screen.getByLabelText("To Node"), {
      target: { value: junction.id },
    });
    expect(
      within(screen.getByLabelText("To Node")).getByText("SWGR-1 · LINE"),
    ).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Nominal Voltage"), {
      target: { value: "600.12345678901234567890123456789" },
    });
    expect(
      within(screen.getByLabelText("Voltage Input Unit")).getByText("MV"),
    ).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Voltage Input Unit"), {
      target: { value: "V" },
    });
    fireEvent.click(screen.getByText("Create connection"));
    await waitFor(() =>
      expect(api.createConnection).toHaveBeenCalledWith(
        "p",
        "r",
        expect.objectContaining({
          nominal_voltage: "600.12345678901234567890123456789",
          nominal_voltage_unit: "V",
        }),
      ),
    );
  });
  it("edits only changed connection fields and explicitly clears voltage", async () => {
    mount(
      <ConnectionEditorSheet
        row={connection}
        nodes={[terminal, junction]}
        labels={new Map()}
        onClose={vi.fn()}
      />,
    );
    expect(screen.getByText("Save connection")).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Nominal Voltage"), {
      target: { value: "" },
    });
    fireEvent.click(screen.getByText("Save connection"));
    await waitFor(() =>
      expect(api.updateConnection).toHaveBeenCalledWith("p", "r", "c1", {
        nominal_voltage: null,
        nominal_voltage_unit: null,
      }),
    );
  });
  it("hides all mutations while read-only and blocks terminals under removed Equipment", async () => {
    context.writable = false;
    const view = mount(
      <>
        <EquipmentGeneralPanel row={equipment} onSaved={vi.fn()} />
        <EquipmentTerminalsPanel row={equipment} />
        <TopologyWorkspace />
      </>,
    );
    await screen.findByText("LINE · Active");
    expect(
      screen.queryByRole("button", {
        name: /^(Add |Save |Remove |Restore |Edit )/,
      }),
    ).not.toBeInTheDocument();
    view.unmount();
    context.writable = true;
    mount(
      <EquipmentTerminalsPanel
        row={{ ...equipment, lifecycle_status: "REMOVED" }}
      />,
    );
    await screen.findByText("Restore equipment before changing its terminals.");
    expect(screen.queryByText("Restore terminal")).not.toBeInTheDocument();
  });
});
