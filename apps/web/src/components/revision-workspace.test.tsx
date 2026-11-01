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
const nav = vi.hoisted(() => ({
  search: "",
  replace: vi.fn(),
  push: vi.fn(),
  refresh: vi.fn(),
}));
vi.mock("next/navigation", () => ({
  useRouter: () => nav,
  usePathname: () => "/projects/p/revisions/r",
  useSearchParams: () => new URLSearchParams(nav.search),
  notFound: () => {
    throw new Error("not found");
  },
}));
vi.mock("next/link", () => ({
  default: ({
    children,
    href,
  }: {
    children: React.ReactNode;
    href: string;
  }) => <a href={href}>{children}</a>,
}));
vi.mock("@/components/revision-documents", () => ({
  RevisionDocuments: ({ readOnlyReason }: { readOnlyReason?: string | null }) => (
    <div data-read-only={readOnlyReason ?? ""}>Existing Documents workspace</div>
  ),
}));
vi.mock("@/lib/engineering-model", async (original) => ({
  ...(await original<typeof api>()),
  getEngineeringRegistry: vi.fn(),
  listEquipment: vi.fn(),
  getEquipmentEditor: vi.fn(),
  saveEquipmentEditor: vi.fn(),
  removeEquipment: vi.fn(),
  restoreEquipment: vi.fn(),
  listAttributes: vi.fn(),
  listNodes: vi.fn(),
  listConnections: vi.fn(),
}));
vi.mock("@/lib/projects", async (original) => ({
  ...(await original<typeof import("@/lib/projects")>()),
  getProject: vi.fn(),
  getRevision: vi.fn(),
  listRevisions: vi.fn().mockResolvedValue([]),
}));
import { RevisionWorkspace } from "@/components/revision-workspace";
import RevisionPage from "@/app/projects/[projectId]/revisions/[revisionId]/page";
import {
  attributes,
  connection,
  equipment,
  junction,
  registry,
  terminal,
} from "@/components/model-test-fixtures";
import * as api from "@/lib/engineering-model";
import {
  getProject,
  getRevision,
  listRevisions,
  type Project,
  type Revision,
} from "@/lib/projects";
const props = {
  projectId: "p",
  revisionId: "r",
  canMutate: true,
  revisionLabel: "B",
};
const path = "/projects/p/revisions/r";
const editUrl = "workspace=model&equipment=e1&equipmentMode=edit";
/** Apply the last client navigation to the mocked URL, as the router would. */
function follow(
  view: { rerender: (ui: React.ReactElement) => void },
  method: "replace" | "push" = "replace",
) {
  const url: string = nav[method].mock.lastCall![0];
  nav.search = url.split("?")[1] ?? "";
  view.rerender(<RevisionWorkspace {...props} />);
}
beforeEach(() => {
  vi.resetAllMocks();
  nav.search = "";
  vi.mocked(listRevisions).mockResolvedValue([]);
  vi.mocked(api.getEngineeringRegistry).mockResolvedValue(registry);
  vi.mocked(api.listEquipment).mockResolvedValue([equipment]);
  vi.mocked(api.getEquipmentEditor).mockResolvedValue({
    equipment,
    attributes,
    terminals: [terminal],
  });
  vi.mocked(api.listAttributes).mockResolvedValue(attributes);
  vi.mocked(api.listNodes).mockResolvedValue([terminal, junction]);
  vi.mocked(api.listConnections).mockResolvedValue([connection]);
});
const inspector = () =>
  screen.findByRole("complementary", { name: "Equipment quick details" });
describe("revision model workspace", () => {
  it("defaults to Documents and switches URL state without dropping unrelated parameters", async () => {
    nav.search = "document=d1&keep=yes";
    const view = render(<RevisionWorkspace {...props} />);
    expect(
      screen.getByText("Existing Documents workspace"),
    ).toBeInTheDocument();
    expect(api.getEngineeringRegistry).not.toHaveBeenCalled();
    // Documents owns its header; the sidebar switches to the model.
    expect(
      screen.queryByRole("group", { name: "Revision workspace" }),
    ).not.toBeInTheDocument();
    nav.search = "keep=yes&workspace=model&equipment=e1";
    view.rerender(<RevisionWorkspace {...props} />);
    await inspector();
    // Equipment owns the page header; shell navigation replaces the toggles.
    expect(
      screen.queryByRole("group", { name: "Revision workspace" }),
    ).not.toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: "Close equipment details" }),
    );
    expect(nav.replace).toHaveBeenLastCalledWith(
      `${path}?keep=yes&workspace=model`,
      { scroll: false },
    );
    nav.search = "keep=yes&workspace=model&view=topology";
    view.rerender(<RevisionWorkspace {...props} />);
    fireEvent.click(
      within(
        screen.getByRole("group", { name: "Revision workspace" }),
      ).getByText("Documents"),
    );
    expect(nav.replace).toHaveBeenLastCalledWith(`${path}?keep=yes`, {
      scroll: false,
    });
    nav.search = "keep=yes";
    view.rerender(<RevisionWorkspace {...props} />);
    expect(screen.getByText("Existing Documents workspace")).toBeVisible();
    nav.search = "workspace=model";
    view.rerender(<RevisionWorkspace {...props} />);
    expect(api.getEngineeringRegistry).toHaveBeenCalledTimes(1);
  });
  it("loads registry filter choices, opens rows by keyboard, and applies server filters", async () => {
    nav.search = "workspace=model";
    render(<RevisionWorkspace {...props} />);
    await screen.findByText("SWGR-1");
    fireEvent.keyDown(screen.getByLabelText("Filter by type"), {
      key: "ArrowDown",
    });
    expect(
      screen.getByRole("option", { name: "Registry Device" }),
    ).toHaveAttribute("data-value", "TEST_DEVICE");
    fireEvent.keyDown(screen.getByRole("listbox"), { key: "Escape" });
    await changeField(screen.getByLabelText("Filter by type"), {
      target: { value: "ALTERNATE" },
    });
    await changeField(screen.getByLabelText("Filter by status"), {
      target: { value: "REMOVED" },
    });
    await waitFor(() =>
      expect(api.listEquipment).toHaveBeenLastCalledWith("p", "r", {
        search: "",
        equipment_type: "ALTERNATE",
        lifecycle_status: "REMOVED",
      }),
    );
    await changeField(screen.getByLabelText("Filter by status"), {
      target: { value: "ALL" },
    });
    await waitFor(() =>
      expect(api.listEquipment).toHaveBeenLastCalledWith(
        "p",
        "r",
        expect.objectContaining({ lifecycle_status: "ALL" }),
      ),
    );
    fireEvent.keyDown(screen.getByText("SWGR-1").closest("tr")!, {
      key: "Enter",
    });
    expect(nav.replace).toHaveBeenLastCalledWith(
      `${path}?workspace=model&equipment=e1`,
      { scroll: false },
    );
  });
  it("shows truthful counts from one unfiltered lifecycle query", async () => {
    nav.search = "workspace=model";
    const removed = {
      ...equipment,
      id: "e2",
      tag: "OLD-1",
      lifecycle_status: "REMOVED" as const,
    };
    vi.mocked(api.listEquipment).mockImplementation(async (_p, _r, query) =>
      query?.lifecycle_status === "ALL"
        ? [equipment, removed]
        : query?.lifecycle_status === "REMOVED"
          ? [removed]
          : [equipment],
    );
    render(<RevisionWorkspace {...props} />);
    expect(
      await screen.findByText("Showing 1 of 1 equipment", { exact: false }),
    ).toBeInTheDocument();
    const metric = (label: string) =>
      screen.getByRole("group", { name: label });
    expect(metric("Total equipment")).toHaveTextContent("2");
    expect(metric("Active")).toHaveTextContent("1");
    expect(metric("Removed")).toHaveTextContent("1");
    expect(api.listEquipment).toHaveBeenCalledWith("p", "r", {
      lifecycle_status: "ALL",
    });
    expect(
      screen.getByText("Manage electrical equipment in revision B"),
    ).toBeInTheDocument();
  });
  it("debounces server search and ignores superseded responses", async () => {
    nav.search = "workspace=model";
    let finishOld!: (value: api.Equipment[]) => void;
    vi.mocked(api.listEquipment).mockImplementation((_p, _r, query) =>
      query?.search === "old"
        ? new Promise((resolve) => {
            finishOld = resolve;
          })
        : Promise.resolve([{ ...equipment, tag: query?.search || "Initial" }]),
    );
    render(<RevisionWorkspace {...props} />);
    await screen.findByText("Initial");
    const calls = vi.mocked(api.listEquipment).mock.calls.length;
    await changeField(
      screen.getByRole("textbox", { name: "Search equipment" }),
      { target: { value: "old" } },
    );
    expect(api.listEquipment).toHaveBeenCalledTimes(calls);
    await waitFor(() =>
      expect(api.listEquipment).toHaveBeenLastCalledWith(
        "p",
        "r",
        expect.objectContaining({ search: "old" }),
      ),
    );
    await changeField(
      screen.getByRole("textbox", { name: "Search equipment" }),
      { target: { value: "latest" } },
    );
    await screen.findByText("latest");
    await act(async () => finishOld([{ ...equipment, tag: "Stale" }]));
    expect(screen.queryByText("Stale")).not.toBeInTheDocument();
  });
  it("opens nonmodal quick details from deep links via GET and keeps the register usable", async () => {
    nav.search = "workspace=model&equipment=e1&keep=1";
    vi.mocked(api.listEquipment).mockResolvedValue([
      equipment,
      { ...equipment, id: "e2", tag: "SWGR-2" },
    ]);
    render(<RevisionWorkspace {...props} />);
    const details = within(await inspector());
    expect(api.getEquipmentEditor).toHaveBeenCalledWith("p", "r", "e1");
    expect(
      await details.findByRole("heading", { name: "SWGR-1" }),
    ).toBeVisible();
    expect(details.getByText("Registry Device")).toBeInTheDocument();
    expect(details.getByText("ENGINEER_REVIEWED")).toBeInTheDocument();
    // Critical registry attribute, shown with its truthful state.
    expect(details.getByText("Count")).toBeInTheDocument();
    expect(details.getAllByText("Not populated").length).toBeGreaterThan(0);
    expect(await details.findByText("1 active connection")).toBeInTheDocument();
    expect(details.getByText(/LINE ↔/)).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    fireEvent.click(screen.getByText("SWGR-2"));
    expect(nav.replace).toHaveBeenLastCalledWith(
      `${path}?workspace=model&equipment=e2&keep=1`,
      { scroll: false },
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Close equipment details" }),
    );
    expect(nav.replace).toHaveBeenLastCalledWith(
      `${path}?workspace=model&keep=1`,
      { scroll: false },
    );
  });
  it("clears a missing equipment deep link and shows the safe message", async () => {
    nav.search = "workspace=model&equipment=missing";
    vi.mocked(api.getEquipmentEditor).mockRejectedValue(
      Object.assign(new Error("Equipment not found"), {
        status: 404,
        apiError: {
          detail: "Equipment not found",
          code: "equipment_not_found",
        },
      }),
    );
    const view = render(<RevisionWorkspace {...props} />);
    await waitFor(() =>
      expect(nav.replace).toHaveBeenCalledWith(`${path}?workspace=model`, {
        scroll: false,
      }),
    );
    nav.search = "workspace=model";
    view.rerender(<RevisionWorkspace {...props} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Equipment not found");
  });
  it("clears a missing equipment editor link", async () => {
    nav.search = `${editUrl}&equipmentTab=terminals`;
    vi.mocked(api.getEquipmentEditor).mockRejectedValue(
      Object.assign(new Error("Equipment not found"), {
        status: 404,
        apiError: { detail: "Equipment not found" },
      }),
    );
    render(<RevisionWorkspace {...props} />);
    await waitFor(() =>
      expect(nav.replace).toHaveBeenCalledWith(`${path}?workspace=model`, {
        scroll: false,
      }),
    );
  });
  it("retries registry loading without affecting Documents", async () => {
    nav.search = "workspace=model";
    vi.mocked(api.getEngineeringRegistry).mockRejectedValueOnce(
      new Error("Registry unavailable"),
    );
    render(<RevisionWorkspace {...props} />);
    await screen.findByText("Registry unavailable");
    fireEvent.click(screen.getByText("Retry"));
    await screen.findByText("SWGR-1");
  });
  it("opens the full editor by URL, switches tabs, and returns to quick details", async () => {
    nav.search = "workspace=model&equipment=e1";
    const view = render(<RevisionWorkspace {...props} />);
    const details = within(await inspector());
    await details.findByRole("heading", { name: "SWGR-1" });
    fireEvent.click(details.getByRole("button", { name: "Open full editor" }));
    expect(nav.push).toHaveBeenLastCalledWith(
      `${path}?${editUrl}&equipmentTab=general`,
      { scroll: false },
    );
    follow(view, "push");
    await screen.findByLabelText("Equipment tag");
    expect(
      screen.getByRole("heading", { level: 1, name: /SWGR-1/ }),
    ).toBeVisible();
    expect(
      screen.queryByRole("complementary", { name: "Equipment quick details" }),
    ).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "Terminals" }));
    expect(nav.replace).toHaveBeenLastCalledWith(
      `${path}?${editUrl}&equipmentTab=terminals`,
      { scroll: false },
    );
    follow(view);
    expect(screen.getByRole("tab", { name: "Terminals" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(screen.getByRole("group", { name: "Terminal LINE" })).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Back to Equipment" }));
    expect(nav.replace).toHaveBeenLastCalledWith(
      `${path}?workspace=model&equipment=e1`,
      { scroll: false },
    );
    follow(view);
    expect(await inspector()).toBeVisible();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
  it("guards a dirty draft when Back/Forward leaves the editor", async () => {
    nav.search = `${editUrl}&equipmentTab=general`;
    const view = render(<RevisionWorkspace {...props} />);
    await changeField(await screen.findByLabelText("Equipment tag"), {
      target: { value: "Draft tag" },
    });
    nav.search = "workspace=model&equipment=e1";
    view.rerender(<RevisionWorkspace {...props} />);
    const dialog = screen.getByRole("dialog", { name: "Unsaved changes" });
    fireEvent.click(within(dialog).getByText("Keep editing"));
    expect(nav.replace).toHaveBeenLastCalledWith(
      `${path}?${editUrl}&equipmentTab=general`,
      { scroll: false },
    );
    follow(view);
    expect(screen.getByLabelText("Equipment tag")).toHaveValue("Draft tag");
    nav.search = "workspace=model&equipment=e1";
    view.rerender(<RevisionWorkspace {...props} />);
    fireEvent.click(screen.getByText("Discard changes"));
    expect(await inspector()).toBeVisible();
    expect(screen.queryByLabelText("Equipment tag")).not.toBeInTheDocument();
    expect(api.saveEquipmentEditor).not.toHaveBeenCalled();
  });
  it("shows Restore for removed equipment and confirms cascade consequences for active removal", async () => {
    nav.search = `${editUrl}&equipmentTab=general`;
    vi.mocked(api.getEquipmentEditor).mockResolvedValue({
      equipment: { ...equipment, lifecycle_status: "REMOVED" },
      attributes,
      terminals: [],
    });
    const view = render(<RevisionWorkspace {...props} />);
    fireEvent.click(await screen.findByText("Restore equipment"));
    await waitFor(() =>
      expect(api.restoreEquipment).toHaveBeenCalledWith("p", "r", "e1"),
    );
    expect(screen.getByRole("button", { name: "Save changes" })).toBeDisabled();
    view.unmount();
    vi.mocked(api.getEquipmentEditor).mockResolvedValue({
      equipment,
      attributes,
      terminals: [],
    });
    render(<RevisionWorkspace {...props} />);
    fireEvent.click(await screen.findByText("Remove equipment"));
    const dialog = screen.getByRole("dialog", { name: "Remove equipment?" });
    expect(dialog).toHaveTextContent(
      "terminal nodes and active incident connections",
    );
    expect(dialog).toHaveTextContent("does not automatically restore");
    fireEvent.click(within(dialog).getByText("Remove equipment"));
    await waitFor(() => expect(api.removeEquipment).toHaveBeenCalled());
  });
  it("refreshes attributes after a successful type change", async () => {
    nav.search = `${editUrl}&equipmentTab=attributes`;
    vi.mocked(api.saveEquipmentEditor).mockImplementation(async () => {
      const changed = {
        ...equipment,
        equipment_type: "ALTERNATE",
        updated_at: "2026-02-01",
      };
      const result = { equipment: changed, attributes: [], terminals: [] };
      vi.mocked(api.getEquipmentEditor).mockResolvedValue(result);
      return result;
    });
    const view = render(<RevisionWorkspace {...props} />);
    await screen.findByRole("group", { name: "Rated voltage" });
    nav.search = `${editUrl}&equipmentTab=general`;
    view.rerender(<RevisionWorkspace {...props} />);
    await changeField(screen.getByLabelText("Equipment type"), {
      target: { value: "ALTERNATE" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(api.saveEquipmentEditor).toHaveBeenCalled());
    await waitFor(() =>
      expect(screen.getByLabelText("Equipment type")).toHaveTextContent(
        "Alternate",
      ),
    );
    nav.search = `${editUrl}&equipmentTab=attributes`;
    view.rerender(<RevisionWorkspace {...props} />);
    // The confirmed atomic save response replaces the cached snapshot directly.
    expect(api.getEquipmentEditor).toHaveBeenCalledTimes(1);
    expect(
      screen.queryByRole("group", { name: "Rated voltage" }),
    ).not.toBeInTheDocument();
  });
  it("locks locally and refreshes after a stale read-only response", async () => {
    nav.search = `${editUrl}&equipmentTab=general`;
    vi.mocked(api.saveEquipmentEditor).mockRejectedValue(
      Object.assign(new Error("Revision is read-only"), {
        status: 409,
        apiError: {
          code: "revision_read_only",
          detail: "Revision is read-only",
        },
      }),
    );
    render(<RevisionWorkspace {...props} />);
    await waitFor(() => expect(api.listEquipment).toHaveBeenCalledTimes(2));
    await changeField(await screen.findByLabelText("Equipment tag"), {
      target: { value: "Changed" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await screen.findByText(
      "This revision is read-only. Further edits are unavailable.",
    );
    expect(nav.refresh).toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Save changes" })).toBeDisabled();
    expect(screen.queryByText("Add Equipment")).not.toBeInTheDocument();
    // Register and summary queries both refetch after the 409 invalidation.
    await waitFor(() => expect(api.listEquipment).toHaveBeenCalledTimes(4));
  });
  it("lets Documents own its read-only notice", async () => {
    nav.search = "";
    vi.mocked(getProject).mockResolvedValue({
      id: "p",
      status: "ACTIVE",
      project_name: "Test project",
      project_number: "TEST",
    } as Project);
    vi.mocked(getRevision).mockResolvedValue({
      id: "r",
      identifier: "0",
      status: "SUPERSEDED",
      created_at: "2026-01-01",
      updated_at: "2026-01-01",
    } as Revision);
    render(
      await RevisionPage({
        params: Promise.resolve({ projectId: "p", revisionId: "r" }),
      }),
    );
    const documents = screen.getByText("Existing Documents workspace");
    expect(documents.getAttribute("data-read-only")).not.toBe("");
    expect(
      screen.queryByText(/Engineering model data remains viewable/),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("group", { name: "Revision workspace" }),
    ).not.toBeInTheDocument();
  });
  it("keeps the shared read-only banner above the Equipment workspace", async () => {
    nav.search = "workspace=model";
    vi.mocked(getProject).mockResolvedValue({
      id: "p",
      status: "ACTIVE",
      project_name: "Test project",
      project_number: "TEST",
    } as Project);
    vi.mocked(getRevision).mockResolvedValue({
      id: "r",
      identifier: "0",
      status: "SUPERSEDED",
      created_at: "2026-01-01",
      updated_at: "2026-01-01",
    } as Revision);
    render(
      await RevisionPage({
        params: Promise.resolve({ projectId: "p", revisionId: "r" }),
      }),
    );
    const banner = screen.getByText(/Engineering model data remains viewable/);
    const workspace = await screen.findByRole("heading", {
      level: 1,
      name: "Equipment",
    });
    expect(
      banner.compareDocumentPosition(workspace) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    await screen.findByText("SWGR-1");
    expect(screen.queryByText("Add Equipment")).not.toBeInTheDocument();
    expect(
      screen.getByText("Manage electrical equipment in revision 0"),
    ).toBeInTheDocument();
  });
});
