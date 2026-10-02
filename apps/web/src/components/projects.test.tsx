/** @vitest-environment jsdom */
import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: vi.fn(),
    refresh: vi.fn(),
  }),
}));

vi.mock("next/link", () => ({
  default: ({
    href,
    children,
    ...props
  }: {
    href: string;
    children: React.ReactNode;
  }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

import { CreateProjectForm } from "@/components/create-project-form";
import { ProjectDetail } from "@/components/project-detail";
import { ProjectList } from "@/components/project-list";
import type { Project, Revision } from "@/lib/projects";

const sampleProject: Project = {
  id: "11111111-1111-1111-1111-111111111111",
  project_number: "2026-001",
  project_name: "ABC Hospital",
  project_address: "123 Main",
  project_scope: "Arc flash",
  client_name: "ABC Engineering",
  description: "Study",
  engineer_names: ["Bob Smith"],
  status: "ACTIVE",
  created_at: "2026-09-01T00:00:00Z",
  updated_at: "2026-09-02T00:00:00Z",
  archived_at: null,
  status_before_archive: null,
  created_by: null,
  active_revision_identifier: "REV-1",
};

const sampleRevision: Revision = {
  id: "22222222-2222-2222-2222-222222222222",
  project_id: sampleProject.id,
  identifier: "REV-1",
  description: "Initial",
  status: "ACTIVE",
  created_at: "2026-09-01T00:00:00Z",
  updated_at: "2026-09-01T00:00:00Z",
  created_by: null,
};

describe("ProjectList", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("renders project rows", () => {
    render(<ProjectList initialProjects={[sampleProject]} />);
    expect(screen.getByText("2026-001")).toBeInTheDocument();
    expect(screen.getByText("ABC Hospital")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /New Project/i })).toBeInTheDocument();
  });

  it("shows an error when refresh fails", async () => {
    const user = userEvent.setup();
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: false,
      status: 500,
      statusText: "Server Error",
      json: async () => ({ detail: "boom" }),
    } as Response);

    render(<ProjectList initialProjects={[sampleProject]} />);
    await user.click(screen.getByRole("button", { name: "Refresh" }));
    await waitFor(() => {
      expect(screen.getByText("boom")).toBeInTheDocument();
    });
  });
});

describe("CreateProjectForm", () => {
  it("posts project create payload", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      status: 201,
      json: async () => sampleProject,
    } as Response);

    render(<CreateProjectForm />);
    await user.type(screen.getByLabelText(/Project Number/i), "2026-010");
    await user.type(screen.getByLabelText(/Project Name/i), "Plant");
    await user.click(screen.getByRole("button", { name: "Create Project" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalled();
    });
    const [, init] = fetchMock.mock.calls[0]!;
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toMatchObject({
      project_number: "2026-010",
      project_name: "Plant",
    });
  });

  it("shows API error on create failure", async () => {
    const user = userEvent.setup();
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: false,
      status: 409,
      statusText: "Conflict",
      json: async () => ({
        detail: { detail: "Project number already exists", code: "duplicate_project_number" },
      }),
    } as Response);

    render(<CreateProjectForm />);
    await user.type(screen.getByLabelText(/Project Number/i), "DUP");
    await user.type(screen.getByLabelText(/Project Name/i), "Dup");
    await user.click(screen.getByRole("button", { name: "Create Project" }));

    await waitFor(() => {
      expect(screen.getByText("Project number already exists")).toBeInTheDocument();
    });
  });
});

describe("ProjectDetail", () => {
  it("renders detail and activates a draft revision", async () => {
    const user = userEvent.setup();
    const draft: Revision = {
      ...sampleRevision,
      id: "33333333-3333-3333-3333-333333333333",
      identifier: "REV-2",
      status: "DRAFT",
      created_at: "2026-09-02T00:00:00Z",
      updated_at: "2026-09-02T00:00:00Z",
    };
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ ...draft, status: "ACTIVE" }),
    } as Response);

    render(
      <ProjectDetail initialProject={sampleProject} initialRevisions={[sampleRevision, draft]} />,
    );
    expect(screen.getByRole("heading", { name: "ABC Hospital" })).toBeInTheDocument();
    expect(screen.getByText("Revision History")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Activate" }));
    await waitFor(() => {
      expect(screen.getByText(/Revision REV-2 is now ACTIVE/i)).toBeInTheDocument();
    });
  });

  it("archives a project via lifecycle action", async () => {
    const user = userEvent.setup();
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        ...sampleProject,
        status: "ARCHIVED",
        archived_at: "2026-09-03T00:00:00Z",
      }),
    } as Response);

    render(<ProjectDetail initialProject={sampleProject} initialRevisions={[sampleRevision]} />);
    await user.click(screen.getByRole("button", { name: "Project actions" }));
    await user.click(screen.getByRole("menuitem", { name: "Archive" }));

    const dialog = screen.getByRole("dialog");
    await user.click(dialog.querySelector("button:last-of-type") as HTMLButtonElement);

    await waitFor(() => {
      expect(screen.getByText(/Project is now ARCHIVED/i)).toBeInTheDocument();
    });
  });
});
