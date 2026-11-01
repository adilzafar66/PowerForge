import { changeField } from "@/components/ui/control-test-helpers";
/** @vitest-environment jsdom */
import React from "react";
import Link from "next/link";
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@/components/query-test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { guardNavigation } from "@/lib/navigation-guard";
import { keys } from "@/lib/query-keys";
import {
  ModelContext,
  type ModelContextValue,
} from "@/components/model-shared";
import { EquipmentGeneralPanel } from "@/components/equipment-general-panel";
import { EquipmentEditorHarness } from "@/components/equipment-editor-test-utils";
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
async function editor(tab = "General", onLeft = vi.fn()) {
  const view = mount(
    <EquipmentEditorHarness id={equipment.id} onLeft={onLeft} />,
  );
  await screen.findByLabelText("Equipment tag");
  if (tab !== "General") openTab(tab);
  return view;
}
const openTab = (name: string) =>
  fireEvent.click(screen.getByRole("tab", { name }));
const back = () =>
  fireEvent.click(screen.getByRole("button", { name: "Back to Equipment" }));
const save = () => screen.getByRole("button", { name: "Save changes" });
const group = (name: string) => within(screen.getByRole("group", { name }));
describe("unified equipment editor", () => {
  it("preserves an unsaved draft and its baseline across a cache refetch", async () => {
    const view = await editor();
    await changeField(screen.getByLabelText("Equipment tag"), {
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
    expect(screen.getByLabelText("Equipment tag")).toHaveValue(
      "My unsaved tag",
    );
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
    await changeField(screen.getByLabelText("Equipment tag"), {
      target: { value: "" },
    });
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
    await changeField(screen.getByLabelText("Equipment tag"), {
      target: { value: "Changed" },
    });
    openTab("Attributes");
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
    openTab("Terminals");
    fireEvent.click(screen.getByText("Add Custom Terminal"));
    const custom = group("Terminal new");
    await changeField(custom.getByLabelText("Terminal key"), {
      target: { value: "GROUND" },
    });
    openTab("General");
    expect(screen.getByLabelText("Equipment tag")).toHaveValue("Changed");
    openTab("Attributes");
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
      expect(field.getByLabelText("Value")).toBeDisabled();
      expect(field.getByLabelText("Value")).toHaveValue("");
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
  it("preserves draft on a failed save and failed save-and-leave", async () => {
    vi.mocked(api.saveEquipmentEditor).mockRejectedValue(
      new Error("Meaningful attributes prevent type change"),
    );
    const left = vi.fn();
    await editor("General", left);
    await changeField(screen.getByLabelText("Equipment type"), {
      target: { value: "ALTERNATE" },
    });
    fireEvent.click(save());
    await screen.findByText("Meaningful attributes prevent type change");
    expect(screen.getByLabelText("Equipment type")).toHaveTextContent(
      "Alternate",
    );
    back();
    fireEvent.click(screen.getByRole("button", { name: "Save and leave" }));
    await waitFor(() =>
      expect(api.saveEquipmentEditor).toHaveBeenCalledTimes(2),
    );
    expect(left).not.toHaveBeenCalled();
    expect(context.failed).toHaveBeenCalled();
    expect(
      screen.getByRole("dialog", { name: "Unsaved changes" }),
    ).toBeInTheDocument();
  });
  it("returns immediately without a draft", async () => {
    const left = vi.fn();
    await editor("General", left);
    back();
    expect(left).toHaveBeenCalledOnce();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
  it("protects a dirty return with keep editing, discard, and save choices", async () => {
    const left = vi.fn();
    await editor("General", left);
    await changeField(screen.getByLabelText("Equipment tag"), {
      target: { value: "Draft" },
    });
    expect(screen.getByText("Unsaved changes")).toBeInTheDocument();
    back();
    expect(
      screen.getByRole("dialog", { name: "Unsaved changes" }),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByText("Keep editing"));
    expect(screen.getByLabelText("Equipment tag")).toHaveValue("Draft");
    expect(left).not.toHaveBeenCalled();
    back();
    fireEvent.click(screen.getByText("Discard changes"));
    expect(left).toHaveBeenCalledOnce();
    expect(api.saveEquipmentEditor).not.toHaveBeenCalled();
  });
  it("leaves only after a successful save-and-leave", async () => {
    const left = vi.fn();
    await editor("General", left);
    await changeField(screen.getByLabelText("Equipment name"), {
      target: { value: "New name" },
    });
    back();
    fireEvent.click(screen.getByRole("button", { name: "Save and leave" }));
    await waitFor(() => expect(left).toHaveBeenCalledOnce());
  });
  describe("navigation away from a dirty editor", () => {
    const editUrl =
      "/projects/p/revisions/r?workspace=model&equipment=e1&equipmentMode=edit";
    const here = () => window.location.pathname + window.location.search;
    beforeEach(() => window.history.replaceState(null, "", editUrl));
    afterEach(() => window.history.replaceState(null, "", "/"));
    async function dirtyEditor() {
      const navigate = vi.fn();
      mount(
        <>
          <Link href="/projects/p">Project overview</Link>
          <EquipmentEditorHarness
            id={equipment.id}
            onLeft={vi.fn()}
            onNavigate={navigate}
          />
        </>,
      );
      await screen.findByLabelText("Equipment tag");
      expect(guardNavigation("/projects/p/revisions/old")).toBe(false);
      await changeField(screen.getByLabelText("Equipment tag"), {
        target: { value: "Draft" },
      });
      return navigate;
    }
    const dialog = () =>
      screen.queryByRole("dialog", { name: "Unsaved changes" });
    it("holds link navigation until the draft is discarded", async () => {
      const navigate = await dirtyEditor();
      const link = screen.getByRole("link", { name: "Project overview" });
      expect(fireEvent.click(link)).toBe(false);
      expect(dialog()).toBeInTheDocument();
      fireEvent.click(screen.getByText("Keep editing"));
      await waitFor(() => expect(dialog()).not.toBeInTheDocument());
      expect(screen.getByLabelText("Equipment tag")).toHaveValue("Draft");
      expect(navigate).not.toHaveBeenCalled();
      fireEvent.click(link);
      fireEvent.click(screen.getByText("Discard changes"));
      expect(navigate).toHaveBeenCalledExactlyOnceWith("/projects/p");
      expect(api.saveEquipmentEditor).not.toHaveBeenCalled();
    });
    it("switches revision only after a successful save", async () => {
      vi.mocked(api.saveEquipmentEditor).mockRejectedValueOnce(
        new Error("Save rejected by server"),
      );
      const navigate = await dirtyEditor();
      act(() => {
        expect(guardNavigation("/projects/p/revisions/old")).toBe(true);
      });
      fireEvent.click(screen.getByRole("button", { name: "Save and leave" }));
      await screen.findAllByText("Save rejected by server");
      expect(navigate).not.toHaveBeenCalled();
      expect(dialog()).toBeInTheDocument();
      fireEvent.click(screen.getByRole("button", { name: "Save and leave" }));
      await waitFor(() =>
        expect(navigate).toHaveBeenCalledExactlyOnceWith(
          "/projects/p/revisions/old",
        ),
      );
      expect(api.saveEquipmentEditor).toHaveBeenCalledTimes(2);
    });
    it("restores the editor entry on browser Back and proceeds on discard", async () => {
      const navigate = await dirtyEditor();
      const router = vi.fn();
      window.addEventListener("popstate", router);
      window.history.pushState(null, "", "/projects/p");
      act(() => {
        window.dispatchEvent(new PopStateEvent("popstate"));
      });
      window.removeEventListener("popstate", router);
      expect(router).not.toHaveBeenCalled();
      expect(here()).toBe(editUrl);
      expect(dialog()).toBeInTheDocument();
      fireEvent.click(screen.getByText("Discard changes"));
      expect(navigate).toHaveBeenCalledExactlyOnceWith("/projects/p");
    });
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
    expect(profile.getByText("INPUT")).toBeInTheDocument();
    expect(profile.queryByLabelText("Terminal key")).not.toBeInTheDocument();
    expect(
      profile.getByText("Application-managed · Active"),
    ).toBeInTheDocument();
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
  it("removes and restores custom terminals through the single editor save", async () => {
    vi.mocked(api.getEquipmentEditor).mockResolvedValue({
      equipment,
      attributes,
      terminals: [
        terminal,
        {
          ...terminal,
          id: "neutral",
          terminal_key: "NEUTRAL",
          lifecycle_status: "REMOVED",
        },
      ],
    });
    await editor("Terminals");
    fireEvent.click(group("Terminal LINE").getByText("Remove terminal"));
    expect(
      screen.getByRole("group", { name: "Terminal LINE" }),
    ).toHaveTextContent("does not automatically restore");
    expect(group("Terminal LINE").getByLabelText("Label")).toBeDisabled();
    fireEvent.click(group("Terminal NEUTRAL").getByText("Restore terminal"));
    fireEvent.click(save());
    await waitFor(() =>
      expect(api.saveEquipmentEditor).toHaveBeenCalledExactlyOnceWith(
        "p",
        "r",
        "e1",
        { remove_terminals: [terminal.id], restore_terminals: ["neutral"] },
      ),
    );
    expect(api.removeNode).not.toHaveBeenCalled();
    expect(api.restoreNode).not.toHaveBeenCalled();
  });
  it("shows CONFLICTING as read-only and does not resubmit it", async () => {
    vi.mocked(api.getEquipmentEditor).mockResolvedValue({
      equipment,
      terminals: [],
      attributes: [
        { ...attributes[0], information_state: "CONFLICTING" },
        ...attributes.slice(1),
      ],
    });
    await editor("Attributes");
    const field = group("Rated voltage");
    expect(field.getByLabelText("Information state")).toHaveTextContent(
      "Conflicting",
    );
    expect(field.getByLabelText("Value")).toBeDisabled();
    fireEvent.keyDown(field.getByLabelText("Information state"), {
      key: "ArrowDown",
    });
    expect(screen.getByRole("option", { name: "Conflicting" })).toHaveAttribute(
      "aria-disabled",
      "true",
    );
    fireEvent.keyDown(screen.getByRole("listbox"), { key: "Escape" });
    expect(save()).toBeDisabled();
  });
  it("filters attributes without changing the draft", async () => {
    await editor("Attributes");
    await changeField(group("Count").getByLabelText("Information state"), {
      target: { value: "PRESENT" },
    });
    await changeField(group("Count").getByLabelText("Value"), {
      target: { value: "9007199254740993" },
    });
    await changeField(screen.getByLabelText("Show"), {
      target: { value: "required" },
    });
    expect(screen.queryByRole("group", { name: "Count" })).toBeNull();
    expect(group("Rated voltage")).toBeTruthy();
    await changeField(screen.getByLabelText("Show"), {
      target: { value: "all" },
    });
    fireEvent.change(screen.getByLabelText("Find an attribute"), {
      target: { value: "coun" },
    });
    expect(screen.queryByRole("group", { name: "Rated voltage" })).toBeNull();
    expect(group("Count").getByLabelText("Value")).toHaveValue(
      "9007199254740993",
    );
    fireEvent.click(save());
    await waitFor(() =>
      expect(api.saveEquipmentEditor).toHaveBeenCalledExactlyOnceWith(
        "p",
        "r",
        "e1",
        {
          attributes: {
            count: { information_state: "PRESENT", value: "9007199254740993" },
          },
        },
      ),
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
      expect(screen.getByLabelText("Equipment tag")).toBeDisabled();
      expect(
        screen.getByText(
          mode === "removed"
            ? "This equipment is removed. Restore it to make changes."
            : /This revision is read-only/,
        ),
      ).toBeInTheDocument();
      openTab("Terminals");
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
