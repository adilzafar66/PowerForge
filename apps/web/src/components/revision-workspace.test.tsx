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
  RevisionDocuments: () => <div>Existing Documents workspace</div>,
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
  equipment,
  registry,
} from "@/components/model-test-fixtures";
import * as api from "@/lib/engineering-model";
import {
  getProject,
  getRevision,
  listRevisions,
  type Project,
  type Revision,
} from "@/lib/projects";
const props = { projectId: "p", revisionId: "r", canMutate: true };
beforeEach(() => {
  vi.resetAllMocks();
  nav.search = "";
  vi.mocked(listRevisions).mockResolvedValue([]);
  vi.mocked(api.getEngineeringRegistry).mockResolvedValue(registry);
  vi.mocked(api.listEquipment).mockResolvedValue([equipment]);
  vi.mocked(api.getEquipmentEditor).mockResolvedValue({
    equipment,
    attributes,
    terminals: [],
  });
  vi.mocked(api.listAttributes).mockResolvedValue(attributes);
});
describe("revision model workspace", () => {
  it("defaults to Documents and switches URL state without dropping unrelated parameters", async () => {
    nav.search = "document=d1&keep=yes";
    const view = render(<RevisionWorkspace {...props} />);
    expect(
      screen.getByText("Existing Documents workspace"),
    ).toBeInTheDocument();
    expect(api.getEngineeringRegistry).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText("Engineering Model"));
    expect(nav.replace).toHaveBeenLastCalledWith(
      "/projects/p/revisions/r?keep=yes&workspace=model",
      { scroll: false },
    );
    nav.search = "keep=yes&workspace=model&equipment=e1";
    view.rerender(<RevisionWorkspace {...props} />);
    await screen.findByLabelText("Tag");
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    nav.search = "keep=yes&workspace=model";
    view.rerender(<RevisionWorkspace {...props} />);
    fireEvent.click(
      within(
        screen.getByRole("group", { name: "Revision workspace" }),
      ).getByText("Documents"),
    );
    expect(nav.replace).toHaveBeenLastCalledWith(
      "/projects/p/revisions/r?keep=yes",
      { scroll: false },
    );
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
    fireEvent.keyDown(screen.getByLabelText("Equipment type filter"), {
      key: "ArrowDown",
    });
    expect(
      screen.getByRole("option", { name: "Registry Device" }),
    ).toHaveAttribute("data-value", "TEST_DEVICE");
    fireEvent.keyDown(screen.getByRole("listbox"), { key: "Escape" });
    await changeField(screen.getByLabelText("Equipment type filter"), {
      target: { value: "ALTERNATE" },
    });
    fireEvent.click(
      within(screen.getByRole("group", { name: "Lifecycle" })).getByText(
        "Removed",
      ),
    );
    await waitFor(() =>
      expect(api.listEquipment).toHaveBeenLastCalledWith("p", "r", {
        search: "",
        equipment_type: "ALTERNATE",
        lifecycle_status: "REMOVED",
      }),
    );
    fireEvent.click(
      within(screen.getByRole("group", { name: "Lifecycle" })).getByText("All"),
    );
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
      "/projects/p/revisions/r?workspace=model&equipment=e1",
      { scroll: false },
    );
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
    await changeField(screen.getByRole("textbox", { name: "Search" }), {
      target: { value: "old" },
    });
    expect(api.listEquipment).toHaveBeenCalledTimes(1);
    await waitFor(() =>
      expect(api.listEquipment).toHaveBeenLastCalledWith(
        "p",
        "r",
        expect.objectContaining({ search: "old" }),
      ),
    );
    await changeField(screen.getByRole("textbox", { name: "Search" }), {
      target: { value: "latest" },
    });
    await screen.findByText("latest");
    await act(async () => finishOld([{ ...equipment, tag: "Stale" }]));
    expect(screen.queryByText("Stale")).not.toBeInTheDocument();
  });
  it("opens deep links via GET independently of visible rows and closes via URL", async () => {
    nav.search = "workspace=model&equipment=e1&keep=1";
    vi.mocked(api.listEquipment).mockResolvedValue([]);
    render(<RevisionWorkspace {...props} />);
    await screen.findByLabelText("Tag");
    expect(api.getEquipmentEditor).toHaveBeenCalledWith("p", "r", "e1");
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(nav.replace).toHaveBeenLastCalledWith(
      "/projects/p/revisions/r?workspace=model&keep=1",
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
      expect(nav.replace).toHaveBeenCalledWith(
        "/projects/p/revisions/r?workspace=model",
        { scroll: false },
      ),
    );
    nav.search = "workspace=model";
    view.rerender(<RevisionWorkspace {...props} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Equipment not found");
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
  it("shows Restore for removed equipment and confirms cascade consequences for active removal", async () => {
    nav.search = "workspace=model&equipment=e1";
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
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
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
    nav.search = "workspace=model&equipment=e1";
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
    render(<RevisionWorkspace {...props} />);
    await screen.findByLabelText("Tag");
    fireEvent.click(screen.getByText("Attributes"));
    await screen.findByRole("group", { name: "Rated voltage" });
    fireEvent.click(screen.getByText("General"));
    await changeField(screen.getByLabelText("Equipment Type"), {
      target: { value: "ALTERNATE" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(api.saveEquipmentEditor).toHaveBeenCalled());
    await waitFor(() =>
      expect(screen.getByLabelText("Equipment Type")).toHaveTextContent(
        "Alternate",
      ),
    );
    fireEvent.click(screen.getByText("Attributes"));
    // The confirmed atomic save response replaces the cached snapshot directly.
    expect(api.getEquipmentEditor).toHaveBeenCalledTimes(1);
    expect(
      screen.queryByRole("group", { name: "Rated voltage" }),
    ).not.toBeInTheDocument();
  });
  it("locks locally and refreshes after a stale read-only response", async () => {
    nav.search = "workspace=model&equipment=e1";
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
    await screen.findByLabelText("Tag");
    await changeField(screen.getByLabelText("Tag"), {
      target: { value: "Changed" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await screen.findByText(
      "This revision is read-only. Further edits are unavailable.",
    );
    expect(nav.refresh).toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
    expect(screen.queryByText("Add Equipment")).not.toBeInTheDocument();
    await waitFor(() => expect(api.listEquipment).toHaveBeenCalledTimes(2));
  });
  it.each(["", "workspace=model"])(
    "keeps the shared read-only banner above workspace %s",
    async (query) => {
      nav.search = query;
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
      const banner = screen.getByText(
        /Engineering model data remains viewable/,
      );
      expect(
        banner.compareDocumentPosition(
          screen.getByRole("group", { name: "Revision workspace" }),
        ) & Node.DOCUMENT_POSITION_FOLLOWING,
      ).toBeTruthy();
      if (query) {
        await screen.findByText("SWGR-1");
        expect(screen.queryByText("Add Equipment")).not.toBeInTheDocument();
      } else
        expect(
          screen.getByText("Existing Documents workspace"),
        ).toBeInTheDocument();
    },
  );
});
