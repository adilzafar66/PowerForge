import { changeField } from "@/components/ui/control-test-helpers";
/** @vitest-environment jsdom */
import React from "react";
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@/components/query-test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { keys } from "@/lib/query-keys";
import {
  ModelContext,
  type ModelContextValue,
} from "@/components/model-shared";
import { EquipmentGeneralPanel } from "@/components/equipment-general-panel";
import { EquipmentDetailDrawer } from "@/components/equipment-detail-drawer";
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
  getEquipmentEditor: vi.fn(),
  saveEquipmentEditor: vi.fn(),
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
    changed: vi.fn(),
    failed: vi.fn(),
  };
  vi.mocked(api.getEquipmentEditor).mockResolvedValue({
    equipment,
    attributes,
    terminals: [terminal],
  });
  vi.mocked(api.saveEquipmentEditor).mockResolvedValue({
    equipment,
    attributes,
    terminals: [terminal],
  });
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
async function editor(tab = "General", onClose = vi.fn()) {
  const view = mount(
    <EquipmentDetailDrawer id={equipment.id} onClose={onClose} />,
  );
  await screen.findByLabelText("Tag");
  if (tab !== "General") fireEvent.click(screen.getByText(tab));
  return view;
}
const save = () => screen.getByRole("button", { name: "Save" });
const group = (name: string) => within(screen.getByRole("group", { name }));
describe("unified equipment editor", () => {
  it("preserves an unsaved draft and its baseline across a cache refetch", async () => {
    const view = await editor();
    await changeField(screen.getByLabelText("Tag"), {
      target: { value: "My unsaved tag" },
    });
    vi.mocked(api.getEquipmentEditor).mockResolvedValue({
      equipment: { ...equipment, tag: "Changed elsewhere" },
      attributes,
      terminals: [terminal],
    });
    await act(() =>
      view.queryClient.invalidateQueries({
        queryKey: keys.editor("p", "r", equipment.id),
      }),
    );
    expect(screen.getByLabelText("Tag")).toHaveValue("My unsaved tag");
    expect(save()).toBeEnabled();
    expect(api.saveEquipmentEditor).not.toHaveBeenCalled();
  });
  it("sends only changed text and resets the draft from the canonical response", async () => {
    vi.mocked(api.saveEquipmentEditor).mockResolvedValue({
      equipment: { ...equipment, tag: null },
      attributes,
      terminals: [terminal],
    });
    await editor();
    expect(save()).toBeDisabled();
    await changeField(screen.getByLabelText("Tag"), { target: { value: "" } });
    fireEvent.click(save());
    await waitFor(() =>
      expect(api.saveEquipmentEditor).toHaveBeenCalledExactlyOnceWith(
        "p",
        "r",
        "e1",
        { general: { tag: null } },
      ),
    );
    await waitFor(() => expect(save()).toBeDisabled());
    expect(api.updateEquipment).not.toHaveBeenCalled();
  });
  it("creates with registry keys and a duplicate-looking tag", async () => {
    mount(<EquipmentGeneralPanel onSaved={vi.fn()} />);
    await changeField(screen.getByLabelText("Tag"), {
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
  it("keeps one draft across tabs and submits General, attributes and custom terminals together", async () => {
    await editor();
    await changeField(screen.getByLabelText("Tag"), {
      target: { value: "Changed" },
    });
    fireEvent.click(screen.getByText("Attributes"));
    expect(
      screen
        .getAllByRole("group")
        .filter((e) =>
          definitions.some(
            (d) => d.display_name === e.getAttribute("aria-label"),
          ),
        )
        .map((e) => e.getAttribute("aria-label")),
    ).toEqual(definitions.map((d) => d.display_name));
    const voltage = group("Rated voltage");
    expect(voltage.getByText("Required")).toBeInTheDocument();
    expect(voltage.queryByText("Critical")).not.toBeInTheDocument();
    expect(group("Count").getByText("Critical")).toBeInTheDocument();
    expect(
      group("Operating mode").getByText("Conditional"),
    ).toBeInTheDocument();
    await changeField(voltage.getByLabelText("Information state"), {
      target: { value: "PRESENT" },
    });
    await changeField(voltage.getByLabelText("Value"), {
      target: { value: "0.1234567890123456789012345678901234" },
    });
    await changeField(voltage.getByLabelText("Input unit"), {
      target: { value: "V" },
    });
    fireEvent.click(screen.getByText("Terminals"));
    fireEvent.click(screen.getByText("Add Custom Terminal"));
    const custom = group("Terminal new");
    await changeField(custom.getByLabelText("Terminal key"), {
      target: { value: "GROUND" },
    });
    fireEvent.click(screen.getByText("General"));
    expect(screen.getByLabelText("Tag")).toHaveValue("Changed");
    fireEvent.click(screen.getByText("Attributes"));
    expect(group("Rated voltage").getByLabelText("Value")).toHaveValue(
      "0.1234567890123456789012345678901234",
    );
    fireEvent.keyDown(document, { key: "s", ctrlKey: true });
    await waitFor(() =>
      expect(api.saveEquipmentEditor).toHaveBeenCalledExactlyOnceWith(
        "p",
        "r",
        "e1",
        {
          general: { tag: "Changed" },
          attributes: {
            voltage: {
              information_state: "PRESENT",
              value: "0.1234567890123456789012345678901234",
              unit: "V",
            },
          },
          create_terminals: [{ terminal_key: "GROUND", label: null }],
        },
      ),
    );
    expect(api.setAttribute).not.toHaveBeenCalled();
    expect(api.createTerminal).not.toHaveBeenCalled();
  });
  it.each(["NOT_POPULATED", "MISSING", "NOT_APPLICABLE"] as const)(
    "saves %s without stale values/units",
    async (state) => {
      vi.mocked(api.getEquipmentEditor).mockResolvedValue({
        equipment,
        terminals: [],
        attributes: [
          {
            ...attributes[0],
            information_state: "PRESENT",
            numeric_value: "600",
          },
          ...attributes.slice(1),
        ],
      });
      await editor("Attributes");
      const field = group("Rated voltage");
      await changeField(field.getByLabelText("Information state"), {
        target: { value: state },
      });
      expect(field.queryByLabelText("Value")).not.toBeInTheDocument();
      fireEvent.click(save());
      await waitFor(() =>
        expect(api.saveEquipmentEditor).toHaveBeenCalledWith("p", "r", "e1", {
          attributes: { voltage: { information_state: state } },
        }),
      );
    },
  );
  it("requires an explicit False choice for an unset boolean", async () => {
    await editor("Attributes");
    const field = group("Enabled");
    await changeField(field.getByLabelText("Information state"), {
      target: { value: "PRESENT" },
    });
    expect(field.getByLabelText("Value")).toHaveTextContent("Select value");
    expect(save()).toBeDisabled();
    fireEvent.click(save());
    fireEvent.keyDown(document, { key: "s", metaKey: true });
    expect(api.saveEquipmentEditor).not.toHaveBeenCalled();
    await changeField(field.getByLabelText("Value"), {
      target: { value: "false" },
    });
    expect(save()).toBeEnabled();

    fireEvent.keyDown(document, { key: "s", metaKey: true });

    await waitFor(() =>
      expect(api.saveEquipmentEditor).toHaveBeenCalledExactlyOnceWith(
        "p",
        "r",
        "e1",
        {
          attributes: {
            enabled: { information_state: "PRESENT", value: false },
          },
        },
      ),
    );
  });
  it("uses registry enum choices and unmodified text", async () => {
    await editor("Attributes");
    for (const [name, value] of [
      ["Operating mode", "CHOICE_B"],
      ["Nameplate note", "Original text"],
    ]) {
      const field = group(name);
      await changeField(field.getByLabelText("Information state"), {
        target: { value: "PRESENT" },
      });
      await changeField(field.getByLabelText("Value"), { target: { value } });
    }
    fireEvent.click(save());
    await waitFor(() =>
      expect(api.saveEquipmentEditor).toHaveBeenCalledWith("p", "r", "e1", {
        attributes: {
          mode: { information_state: "PRESENT", value: "CHOICE_B" },
          note: { information_state: "PRESENT", value: "Original text" },
        },
      }),
    );
  });
  it("preserves draft on a failed save and failed save-and-close", async () => {
    vi.mocked(api.saveEquipmentEditor).mockRejectedValue(
      new Error("Meaningful attributes prevent type change"),
    );
    const close = vi.fn();
    await editor("General", close);
    await changeField(screen.getByLabelText("Equipment Type"), {
      target: { value: "ALTERNATE" },
    });
    fireEvent.click(save());
    await screen.findByText("Meaningful attributes prevent type change");
    expect(screen.getByLabelText("Equipment Type")).toHaveTextContent(
      "Alternate",
    );
    fireEvent.click(screen.getByText("Close"));
    fireEvent.click(screen.getByText("Save changes"));
    await waitFor(() =>
      expect(api.saveEquipmentEditor).toHaveBeenCalledTimes(2),
    );
    expect(close).not.toHaveBeenCalled();
    expect(context.failed).toHaveBeenCalled();
  });
  it("protects dirty close with keep editing, discard, and save choices", async () => {
    const close = vi.fn();
    await editor("General", close);
    await changeField(screen.getByLabelText("Tag"), {
      target: { value: "Draft" },
    });
    fireEvent.keyDown(document, { key: "Escape" });
    expect(
      screen.getByRole("dialog", { name: "Unsaved changes" }),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByText("Keep editing"));
    expect(screen.getByLabelText("Tag")).toHaveValue("Draft");
    expect(close).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText("Close"));
    fireEvent.click(screen.getByText("Discard changes"));
    expect(close).toHaveBeenCalledOnce();
    expect(api.saveEquipmentEditor).not.toHaveBeenCalled();
  });
  it("closes only after successful save-and-close", async () => {
    const close = vi.fn();
    await editor("General", close);
    await changeField(screen.getByLabelText("Name"), {
      target: { value: "New name" },
    });
    fireEvent.click(screen.getByText("Close"));
    fireEvent.click(screen.getByText("Save changes"));
    await waitFor(() => expect(close).toHaveBeenCalledOnce());
  });
  it("keeps custom terminal edits in the draft and protects profile keys", async () => {
    vi.mocked(api.getEquipmentEditor).mockResolvedValue({
      equipment,
      attributes,
      terminals: [
        terminal,
        {
          ...terminal,
          id: "profile",
          terminal_key: "INPUT",
          managed_by_profile: true,
        },
      ],
    });
    await editor("Terminals");
    const profile = group("Terminal INPUT");
    expect(profile.getByLabelText("Terminal key")).toBeDisabled();
    expect(profile.queryByText("Remove terminal")).not.toBeInTheDocument();
    const custom = group("Terminal LINE");
    await changeField(custom.getByLabelText("Label"), {
      target: { value: "Custom label" },
    });
    fireEvent.click(save());
    await waitFor(() =>
      expect(api.saveEquipmentEditor).toHaveBeenCalledWith("p", "r", "e1", {
        update_terminals: [{ id: terminal.id, label: "Custom label" }],
      }),
    );
  });
  it.each(["read-only", "removed"])(
    "disables editing when %s",
    async (mode) => {
      context.writable = mode !== "read-only";
      vi.mocked(api.getEquipmentEditor).mockResolvedValue({
        equipment: {
          ...equipment,
          lifecycle_status: mode === "removed" ? "REMOVED" : "ACTIVE",
        },
        attributes,
        terminals: [terminal],
      });
      await editor();
      expect(save()).toBeDisabled();
      expect(screen.getByLabelText("Tag")).toBeDisabled();
      fireEvent.click(screen.getByText("Terminals"));
      expect(screen.queryByText("Add Custom Terminal")).not.toBeInTheDocument();
    },
  );
});
describe("topology tables", () => {
  it("opens node and connection detail editors from rows, retaining parallel edges", async () => {
    mount(<TopologyWorkspace />);
    const nodes = await screen.findByRole("table", { name: "Nodes" });
    fireEvent.click(within(nodes).getByText("Electrical node · junction"));
    expect(screen.getByRole("dialog")).toHaveTextContent(
      "Electrical Node details",
    );
    await changeField(screen.getByLabelText("Label"), {
      target: { value: "Updated junction" },
    });
    fireEvent.click(screen.getByText("Save node"));
    await waitFor(() =>
      expect(api.updateNode).toHaveBeenCalledWith("p", "r", "junction1", {
        label: "Updated junction",
      }),
    );
    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
    );
    const connections = screen.getByRole("table", { name: "Connections" });
    expect(within(connections).getAllByRole("row")).toHaveLength(3);
    fireEvent.keyDown(within(connections).getAllByRole("row")[1], {
      key: "Enter",
    });
    expect(screen.getByRole("dialog")).toHaveTextContent("Edit Connection");
    fireEvent.click(screen.getByText("Remove connection"));
    await waitFor(() =>
      expect(api.removeConnection).toHaveBeenCalledWith("p", "r", "c1"),
    );
  });
  it("shows managed terminals without rename/removal controls", async () => {
    vi.mocked(api.listNodes).mockResolvedValue([
      { ...terminal, managed_by_profile: true },
      junction,
    ]);
    mount(<TopologyWorkspace />);
    fireEvent.click(
      within(await screen.findByRole("table", { name: "Nodes" })).getByText(
        "SWGR-1 · LINE",
      ),
    );
    expect(screen.getByLabelText(/Terminal key/)).toBeDisabled();
    expect(screen.queryByText("Remove node")).not.toBeInTheDocument();
  });
  it("disables connection restore until both endpoints are active", async () => {
    vi.mocked(api.listConnections).mockResolvedValue([
      { ...connection, lifecycle_status: "REMOVED" },
    ]);
    vi.mocked(api.listNodes).mockResolvedValue([
      terminal,
      { ...junction, lifecycle_status: "REMOVED" },
    ]);
    mount(<TopologyWorkspace />);
    fireEvent.click(
      within(screen.getByRole("group", { name: "Lifecycle" })).getByText("All"),
    );
    fireEvent.click(
      within(
        await screen.findByRole("table", { name: "Connections" }),
      ).getByText("SWGR-1 · LINE"),
    );
    expect(screen.getByText("Restore connection")).toBeDisabled();
    expect(
      screen.getByText("Restore endpoint nodes first."),
    ).toBeInTheDocument();
  });
  it("creates connection with human endpoints and registry units, preserving voltage strings", async () => {
    mount(
      <ConnectionEditorSheet
        nodes={[terminal, junction]}
        labels={api.nodeLabels([terminal, junction], [equipment], registry)}
        onClose={vi.fn()}
      />,
    );
    await changeField(screen.getByLabelText("From Node"), {
      target: { value: terminal.id },
    });
    await changeField(screen.getByLabelText("To Node"), {
      target: { value: junction.id },
    });
    fireEvent.keyDown(screen.getByLabelText("To Node"), { key: "ArrowDown" });
    expect(
      screen.getByRole("option", { name: "SWGR-1 · LINE" }),
    ).toHaveAttribute("aria-disabled", "true");
    fireEvent.keyDown(screen.getByRole("listbox"), { key: "Escape" });
    await changeField(screen.getByLabelText("Nominal Voltage"), {
      target: { value: "600.12345678901234567890123456789" },
    });
    fireEvent.keyDown(screen.getByLabelText("Voltage Input Unit"), {
      key: "ArrowDown",
    });
    expect(screen.getByRole("option", { name: "MV" })).toBeInTheDocument();
    fireEvent.keyDown(screen.getByRole("listbox"), { key: "Escape" });
    await changeField(screen.getByLabelText("Voltage Input Unit"), {
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
    await changeField(screen.getByLabelText("Nominal Voltage"), {
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
});
