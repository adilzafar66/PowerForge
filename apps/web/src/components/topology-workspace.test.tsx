/** @vitest-environment jsdom */
import { changeField } from "@/components/ui/control-test-helpers";
import React from "react";
import userEvent from "@testing-library/user-event";
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@/components/query-test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  ModelContext,
  type ModelContextValue,
} from "@/components/model-shared";
import { ConnectionEditorSheet } from "@/components/connection-editor-sheet";
import { TopologyWorkspace } from "@/components/topology-workspace";
import {
  connection,
  equipment,
  junction,
  registry,
  terminal,
} from "@/components/model-test-fixtures";
import * as api from "@/lib/engineering-model";

const nav = vi.hoisted(() => ({
  search: "workspace=model&view=topology",
  replace: vi.fn(),
  push: vi.fn(),
  refresh: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => nav,
  usePathname: () => "/projects/p/revisions/r",
  useSearchParams: () => new URLSearchParams(nav.search),
}));

vi.mock("@/lib/engineering-model", async (original) => ({
  ...(await original<typeof api>()),
  listNodes: vi.fn(),
  listConnections: vi.fn(),
  listEquipment: vi.fn(),
  updateNode: vi.fn(),
  createElectricalNode: vi.fn(),
  removeNode: vi.fn(),
  restoreNode: vi.fn(),
  createConnection: vi.fn(),
  updateConnection: vi.fn(),
  removeConnection: vi.fn(),
  restoreConnection: vi.fn(),
}));

let context: ModelContextValue;
function mount(child: React.ReactNode = <TopologyWorkspace />) {
  return render(
    <ModelContext.Provider value={context}>{child}</ModelContext.Provider>,
  );
}

function inspector(name: string) {
  return screen.findByRole("dialog", { name });
}

function clickBackdrop(name: string) {
  const dialog = screen.getByRole("dialog", { name });
  return userEvent.click(dialog.previousElementSibling as HTMLElement);
}

beforeEach(() => {
  vi.resetAllMocks();
  nav.search = "workspace=model&view=topology";
  context = {
    projectId: "p",
    revisionId: "r",
    revisionLabel: "B",
    registry,
    writable: true,
    changed: vi.fn(),
    failed: vi.fn(),
  };
  vi.mocked(api.listNodes).mockResolvedValue([terminal, junction]);
  vi.mocked(api.listConnections).mockResolvedValue([
    connection,
    { ...connection, id: "c2" },
  ]);
  vi.mocked(api.listEquipment).mockResolvedValue([equipment]);
  vi.mocked(api.updateNode).mockResolvedValue(junction);
  vi.mocked(api.createElectricalNode).mockResolvedValue(junction);
  vi.mocked(api.removeNode).mockResolvedValue({
    ...junction,
    lifecycle_status: "REMOVED",
  });
  vi.mocked(api.restoreNode).mockResolvedValue(junction);
  vi.mocked(api.createConnection).mockResolvedValue(connection);
  vi.mocked(api.updateConnection).mockResolvedValue(connection);
  vi.mocked(api.removeConnection).mockResolvedValue({
    ...connection,
    lifecycle_status: "REMOVED",
  });
  vi.mocked(api.restoreConnection).mockResolvedValue(connection);
});

describe("topology registers", () => {
  it("shows metrics, search, and parallel connections", async () => {
    mount();
    expect(
      await screen.findByRole("heading", { name: "Topology" }),
    ).toBeInTheDocument();
    await screen.findByRole("table", { name: "Nodes" });
    expect(
      screen.getByText("Electrical nodes and terminals").closest("div"),
    ).toHaveTextContent("2");
    expect(
      screen.getByText("Current topology links").closest("div"),
    ).toHaveTextContent("2");
    expect(
      screen.getByText("History retained").closest("div"),
    ).toHaveTextContent("0");
    expect(
      screen.getByText(/Engineering topology, not a graphical SLD/),
    ).toBeInTheDocument();
    const connections = screen.getByRole("table", { name: "Connections" });
    expect(within(connections).getAllByRole("row")).toHaveLength(3);

    await userEvent.type(screen.getByLabelText("Search topology"), "SWGR");
    expect(
      within(screen.getByRole("table", { name: "Nodes" })).getByText(
        "SWGR-1 · LINE",
      ),
    ).toBeInTheDocument();
    expect(
      within(screen.getByRole("table", { name: "Nodes" })).queryByText(
        /Electrical node/,
      ),
    ).toBeNull();
    expect(
      within(screen.getByRole("table", { name: "Connections" })).getAllByText(
        "SWGR-1 · LINE",
      ).length,
    ).toBeGreaterThan(0);
  });

  it("clears the inspector when the lifecycle filter changes", async () => {
    mount();
    fireEvent.click(
      within(await screen.findByRole("table", { name: "Nodes" })).getByText(
        "Electrical node · junction",
      ),
    );
    expect(await inspector("Electrical node · junction")).toBeInTheDocument();
    await changeField(screen.getByLabelText("Lifecycle"), {
      target: { value: "REMOVED" },
    });
    expect(
      screen.queryByRole("dialog", { name: "Electrical node · junction" }),
    ).toBeNull();
    expect(nav.replace).toHaveBeenCalled();
  });
});

describe("topology inspector", () => {
  it("opens from a row, records the URL, and closes from the overlay", async () => {
    const user = userEvent.setup();
    mount();
    fireEvent.click(
      within(await screen.findByRole("table", { name: "Nodes" })).getByText(
        "Electrical node · junction",
      ),
    );
    const panel = await inspector("Electrical node · junction");
    expect(nav.push).toHaveBeenCalledWith(
      "/projects/p/revisions/r?workspace=model&view=topology&node=junction1",
      { scroll: false },
    );
    expect(within(panel).getByText("Custom / standalone")).toBeInTheDocument();
    await clickBackdrop("Electrical node · junction");
    await waitFor(() =>
      expect(
        screen.queryByRole("dialog", { name: "Electrical node · junction" }),
      ).toBeNull(),
    );
    expect(user).toBeTruthy();
  });

  it("opens a deep-linked connection and hides Remove on a managed terminal", async () => {
    nav.search = "workspace=model&view=topology&connection=c1";
    const view = mount();
    const connectionPanel = await inspector("Connection c1");
    expect(within(connectionPanel).getByText("Electrical")).toBeInTheDocument();
    view.unmount();

    nav.search = "workspace=model&view=topology&node=terminal1";
    vi.mocked(api.listNodes).mockResolvedValue([
      { ...terminal, managed_by_profile: true },
    ]);
    mount();
    const panel = await inspector("SWGR-1 · LINE");
    expect(within(panel).getByText("Application-managed")).toBeInTheDocument();
    expect(within(panel).queryByRole("button", { name: "Remove" })).toBeNull();
    expect(
      within(panel).getByRole("button", { name: "Edit node" }),
    ).toBeInTheDocument();
  });

  it("confirms node remove with the cascade count and does not restore connections", async () => {
    const user = userEvent.setup();
    mount();
    fireEvent.click(
      within(await screen.findByRole("table", { name: "Nodes" })).getByText(
        "Electrical node · junction",
      ),
    );
    await user.click(
      within(await inspector("Electrical node · junction")).getByRole(
        "button",
        {
          name: "Remove",
        },
      ),
    );
    const confirm = await screen.findByRole("dialog", { name: "Remove node?" });
    expect(confirm).toHaveTextContent(
      "Removing this node also removes 2 active incident connections.",
    );
    expect(confirm).toHaveTextContent("will NOT restore");
    await user.click(within(confirm).getByRole("button", { name: "Remove" }));
    await waitFor(() =>
      expect(api.removeNode).toHaveBeenCalledWith("p", "r", "junction1"),
    );
    expect(api.restoreConnection).not.toHaveBeenCalled();
  });

  it("blocks connection restore until both endpoints are active", async () => {
    vi.mocked(api.listConnections).mockResolvedValue([
      { ...connection, lifecycle_status: "REMOVED" },
    ]);
    vi.mocked(api.listNodes).mockResolvedValue([
      terminal,
      { ...junction, lifecycle_status: "REMOVED" },
    ]);
    mount();
    await changeField(await screen.findByLabelText("Lifecycle"), {
      target: { value: "ALL" },
    });
    fireEvent.click(
      within(screen.getByRole("table", { name: "Connections" })).getByText(
        "SWGR-1 · LINE",
      ),
    );
    const panel = await inspector("Connection c1");
    expect(
      within(panel).getByRole("button", { name: "Restore" }),
    ).toBeDisabled();
    expect(
      within(panel).getByText(
        "Restore both endpoint nodes before restoring this connection.",
      ),
    ).toBeInTheDocument();
  });

  it("blocks terminal restore until the owning equipment is active", async () => {
    vi.mocked(api.listEquipment).mockResolvedValue([
      { ...equipment, lifecycle_status: "REMOVED" },
    ]);
    vi.mocked(api.listNodes).mockResolvedValue([
      { ...terminal, lifecycle_status: "REMOVED" },
      junction,
    ]);
    mount();
    await changeField(await screen.findByLabelText("Lifecycle"), {
      target: { value: "ALL" },
    });
    fireEvent.click(
      within(await screen.findByRole("table", { name: "Nodes" })).getByText(
        "SWGR-1 · LINE",
      ),
    );
    const panel = await inspector("SWGR-1 · LINE");
    expect(
      within(panel).getByRole("button", { name: "Restore" }),
    ).toBeDisabled();
    expect(
      within(panel).getByText(
        "Restore the owning equipment before restoring this terminal.",
      ),
    ).toBeInTheDocument();
  });
});

describe("topology editors", () => {
  it("saves a node label from the drawer and guards unsaved edits", async () => {
    const user = userEvent.setup();
    mount();
    fireEvent.click(
      within(await screen.findByRole("table", { name: "Nodes" })).getByText(
        "Electrical node · junction",
      ),
    );
    await user.click(
      within(await inspector("Electrical node · junction")).getByRole(
        "button",
        {
          name: "Edit node",
        },
      ),
    );
    const drawer = await screen.findByRole("dialog", {
      name: "Edit Electrical Node",
    });
    await changeField(within(drawer).getByLabelText("Display label"), {
      target: { value: "Updated junction" },
    });
    await user.click(within(drawer).getByRole("button", { name: "Cancel" }));
    const guard = await screen.findByRole("dialog", {
      name: "Discard unsaved changes?",
    });
    await user.click(
      within(guard).getByRole("button", { name: "Keep editing" }),
    );
    await user.click(
      within(drawer).getByRole("button", { name: "Save changes" }),
    );
    await waitFor(() =>
      expect(api.updateNode).toHaveBeenCalledWith("p", "r", "junction1", {
        label: "Updated junction",
      }),
    );
  });

  it("creates a standalone electrical node with a blank optional label", async () => {
    const user = userEvent.setup();
    mount();
    await user.click(
      await screen.findByRole("button", { name: "Add Electrical Node" }),
    );
    const drawer = await screen.findByRole("dialog", {
      name: "Add Electrical Node",
    });
    expect(within(drawer).getByLabelText("Display label")).toHaveValue("");
    expect(
      within(drawer).getByRole("button", { name: "Create" }),
    ).toBeEnabled();
    await user.click(within(drawer).getByRole("button", { name: "Cancel" }));
    expect(
      screen.queryByRole("dialog", { name: "Discard unsaved changes?" }),
    ).not.toBeInTheDocument();

    await user.click(
      screen.getByRole("button", { name: "Add Electrical Node" }),
    );
    await user.click(
      within(
        await screen.findByRole("dialog", { name: "Add Electrical Node" }),
      ).getByRole("button", { name: "Create" }),
    );
    await waitFor(() =>
      expect(api.createElectricalNode).toHaveBeenCalledWith("p", "r", null),
    );
  });

  it("creates a connection with exact voltage strings and registry units", async () => {
    mount(
      <ConnectionEditorSheet
        nodes={[terminal, junction]}
        labels={api.nodeLabels([terminal, junction], [equipment], registry)}
        onClose={vi.fn()}
      />,
    );
    await changeField(screen.getByLabelText("From node"), {
      target: { value: terminal.id },
    });
    await changeField(screen.getByLabelText("To node"), {
      target: { value: junction.id },
    });
    fireEvent.keyDown(screen.getByLabelText("To node"), { key: "ArrowDown" });
    expect(
      screen.getByRole("option", { name: "SWGR-1 · LINE" }),
    ).toHaveAttribute("aria-disabled", "true");
    fireEvent.keyDown(screen.getByRole("listbox"), { key: "Escape" });
    await changeField(screen.getByLabelText("Nominal voltage"), {
      target: { value: "600.12345678901234567890123456789" },
    });
    fireEvent.keyDown(screen.getByLabelText("Voltage unit"), {
      key: "ArrowDown",
    });
    expect(screen.getByRole("option", { name: "MV" })).toBeInTheDocument();
    fireEvent.keyDown(screen.getByRole("listbox"), { key: "Escape" });
    await changeField(screen.getByLabelText("Voltage unit"), {
      target: { value: "V" },
    });
    fireEvent.submit(screen.getByRole("form", { name: "Connection editor" }));
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

  it("clears voltage on edit and validates identical endpoints", async () => {
    const onClose = vi.fn();
    const view = mount(
      <ConnectionEditorSheet
        row={connection}
        nodes={[terminal, junction]}
        labels={new Map()}
        onClose={onClose}
      />,
    );
    await changeField(screen.getByLabelText("Nominal voltage"), {
      target: { value: "" },
    });
    fireEvent.submit(screen.getByRole("form", { name: "Connection editor" }));
    await waitFor(() =>
      expect(api.updateConnection).toHaveBeenCalledWith("p", "r", "c1", {
        nominal_voltage: null,
        nominal_voltage_unit: null,
      }),
    );
    view.unmount();
    mount(
      <ConnectionEditorSheet
        nodes={[terminal, junction]}
        labels={new Map([[terminal.id, "LINE"]])}
        onClose={vi.fn()}
      />,
    );
    await changeField(screen.getByLabelText("From node"), {
      target: { value: terminal.id },
    });
    fireEvent.keyDown(screen.getByLabelText("From node"), { key: "Escape" });
    fireEvent.submit(screen.getByRole("form", { name: "Connection editor" }));
    expect(
      await screen.findByText("Select two different active endpoint nodes."),
    ).toBeInTheDocument();
  });

  it("hides mutations on a read-only revision", async () => {
    context.writable = false;
    mount(<TopologyWorkspace readOnlyReason="This revision is superseded." />);
    await screen.findByRole("table", { name: "Nodes" });
    expect(screen.getByText("Read-only revision")).toBeInTheDocument();
    expect(
      screen.getByText("This revision is superseded."),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Add Electrical Node" }),
    ).toBeNull();
    fireEvent.click(
      within(screen.getByRole("table", { name: "Nodes" })).getByText(
        "SWGR-1 · LINE",
      ),
    );
    const panel = await inspector("SWGR-1 · LINE");
    expect(
      within(panel).queryByRole("button", { name: "Edit node" }),
    ).toBeNull();
    expect(within(panel).queryByRole("button", { name: "Remove" })).toBeNull();
  });
});
