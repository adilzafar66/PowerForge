import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AppFrame } from "./app-frame";
import { AppShell } from "./app-shell";
import type { Project, Revision } from "@/lib/projects";

const nav = vi.hoisted(() => ({ path: "/", search: "", push: vi.fn() }));
vi.mock("next/navigation", () => ({
  usePathname: () => nav.path,
  useSearchParams: () => new URLSearchParams(nav.search),
  useRouter: () => nav,
}));
const project: Project = {
  id: "p",
  project_number: "100",
  project_name: "Test project",
  project_address: null,
  project_scope: null,
  client_name: null,
  description: null,
  engineer_names: [],
  status: "ACTIVE",
  created_at: "",
  updated_at: "",
  archived_at: null,
  status_before_archive: null,
  created_by: null,
  active_revision_identifier: "A",
};
const revision: Revision = {
  id: "r",
  project_id: "p",
  identifier: "A",
  status: "ACTIVE",
  description: null,
  created_at: "",
  updated_at: "",
  created_by: null,
  based_on_revision_id: null,
  based_on_identifier: null,
  system_frequency: null,
  system_phase_count: null,
};
const revisions = [
  revision,
  { ...revision, id: "next", identifier: "B", status: "DRAFT" as const },
];
beforeEach(() => {
  nav.path = "/";
  nav.search = "";
  nav.push.mockReset();
});

describe("persistent app frame", () => {
  it("shows only supported general navigation without a project", () => {
    render(
      <AppFrame>
        <AppShell>
          <h1>Projects</h1>
        </AppShell>
      </AppFrame>,
    );
    expect(screen.getByRole("link", { name: "Projects" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(screen.getByRole("link", { name: "System Status" })).toHaveAttribute(
      "href",
      "/status",
    );
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
    expect(screen.queryByText("Extraction")).not.toBeInTheDocument();
  });
  it("uses real context and separates revision overview from its switcher", () => {
    nav.path = "/projects/p/revisions/r";
    nav.search = "workspace=model&view=topology&document=old&keep=yes";
    render(
      <AppFrame>
        <AppShell project={project} revision={revision} revisions={revisions}>
          Workspace
        </AppShell>
      </AppFrame>,
    );
    const navigation = within(
      screen.getByRole("navigation", { name: "Main navigation" }),
    );
    expect(navigation.getByRole("link", { name: "Topology" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(navigation.getByRole("link", { name: "A Active" })).toHaveAttribute(
      "href",
      "/projects/p/revisions/r?view=overview&keep=yes",
    );
    fireEvent.keyDown(
      screen.getByRole("combobox", { name: "Switch revision" }),
      { key: "ArrowDown" },
    );
    fireEvent.click(screen.getByRole("option", { name: "B · draft" }));
    expect(nav.push).toHaveBeenCalledWith(
      "/projects/p/revisions/next?workspace=model&view=topology&keep=yes",
    );
  });
  it("opens a named mobile navigation dialog with a working close control", () => {
    render(
      <AppFrame>
        <AppShell>Workspace</AppShell>
      </AppFrame>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Open navigation" }));
    const dialog = screen.getByRole("dialog", { name: "Navigation" });
    expect(
      within(dialog).getByRole("link", { name: "System Status" }),
    ).toHaveAttribute("href", "/status");
    fireEvent.click(
      within(dialog).getByRole("button", { name: "Close navigation" }),
    );
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
