/** @vitest-environment jsdom */
import React from "react";
import { render, screen, waitFor, within } from "@testing-library/react";
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
  based_on_revision_id: null,
  based_on_identifier: null,
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

describe("Create revision form", () => {
  const draft: Revision = {
    ...sampleRevision,
    id: "33333333-3333-3333-3333-333333333333",
    identifier: "REV-2",
    description: "Draft work",
    status: "DRAFT",
    created_at: "2026-09-02T00:00:00Z",
    updated_at: "2026-09-02T00:00:00Z",
  };
  const superseded: Revision = {
    ...sampleRevision,
    id: "44444444-4444-4444-4444-444444444444",
    identifier: "REV-0",
    description: "Original",
    status: "SUPERSEDED",
    created_at: "2026-08-01T00:00:00Z",
    updated_at: "2026-08-01T00:00:00Z",
  };

  async function openForm(revisions: Revision[]) {
    const user = userEvent.setup();
    render(<ProjectDetail initialProject={sampleProject} initialRevisions={revisions} />);
    await user.click(screen.getByRole("button", { name: /Add Revision/ }));
    return user;
  }

  function baseSelect() {
    return screen.getByLabelText("Based on") as HTMLSelectElement;
  }

  function carryBox() {
    return screen.getByRole("checkbox", { name: /Carry forward documents/ }) as HTMLInputElement;
  }

  function mockCreated(extra: Partial<Revision> = {}) {
    return vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      status: 201,
      json: async () => ({
        ...sampleRevision,
        id: "55555555-5555-5555-5555-555555555555",
        identifier: "REV-3",
        description: null,
        status: "DRAFT",
        ...extra,
      }),
    } as Response);
  }

  async function submit(user: ReturnType<typeof userEvent.setup>, fetchMock: ReturnType<typeof mockCreated>) {
    await user.type(screen.getByLabelText(/Revision Identifier/i), "REV-3");
    await user.click(screen.getByRole("button", { name: "Add" }));
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalled();
    });
    const [, init] = fetchMock.mock.calls[0]!;
    expect(init?.method).toBe("POST");
    return JSON.parse(String(init?.body)) as Record<string, unknown>;
  }

  it("defaults to the ACTIVE revision with carry forward checked and no note", async () => {
    await openForm([sampleRevision, draft, superseded]);

    expect(baseSelect().value).toBe(sampleRevision.id);
    expect(
      within(baseSelect())
        .getAllByRole("option")
        .map((option) => option.textContent),
    ).toEqual([
      "None (start fresh)",
      "Revision REV-1 (Active)",
      "Revision REV-2 (Draft)",
      "Revision REV-0 (Superseded)",
    ]);
    expect(carryBox()).toBeChecked();
    expect(carryBox()).toBeEnabled();
    expect(screen.getByRole("checkbox", { name: "Carry forward documents from Revision REV-1" })).toBe(
      carryBox(),
    );
    expect(screen.queryByText(/other than the active one/i)).toBeNull();
  });

  it("selects None and disables carry forward when there is no ACTIVE revision", async () => {
    await openForm([draft, superseded]);

    expect(baseSelect().value).toBe("");
    expect(carryBox()).not.toBeChecked();
    expect(carryBox()).toBeDisabled();
  });

  it("disables and unchecks carry forward when None is chosen, and restores the default for a base", async () => {
    const user = await openForm([sampleRevision, draft]);

    await user.selectOptions(baseSelect(), "None (start fresh)");
    expect(carryBox()).not.toBeChecked();
    expect(carryBox()).toBeDisabled();

    await user.selectOptions(baseSelect(), "Revision REV-2 (Draft)");
    expect(carryBox()).toBeEnabled();
    expect(carryBox()).toBeChecked();
  });

  it("shows a note when the base is not the ACTIVE revision", async () => {
    const user = await openForm([sampleRevision, draft, superseded]);

    await user.selectOptions(baseSelect(), "Revision REV-0 (Superseded)");
    expect(screen.getByText("Based on a revision other than the active one.")).toBeInTheDocument();

    await user.selectOptions(baseSelect(), "Revision REV-1 (Active)");
    expect(screen.queryByText(/other than the active one/i)).toBeNull();
  });

  it("omits the base and carry-forward keys when the user leaves the defaults", async () => {
    const fetchMock = mockCreated();
    const user = await openForm([sampleRevision]);

    const body = await submit(user, fetchMock);

    expect(body).toEqual({ identifier: "REV-3", description: null, activate: false });
  });

  it("sends an explicit null base and no carry forward when None is chosen", async () => {
    const fetchMock = mockCreated();
    const user = await openForm([sampleRevision]);
    await user.selectOptions(baseSelect(), "None (start fresh)");

    const body = await submit(user, fetchMock);

    expect(body.based_on_revision_id).toBeNull();
    expect(body.carry_forward_documents).toBe(false);
  });

  it("sends the chosen base, even when it is the ACTIVE one chosen again", async () => {
    const fetchMock = mockCreated();
    const user = await openForm([sampleRevision, draft]);
    await user.selectOptions(baseSelect(), "Revision REV-2 (Draft)");

    const body = await submit(user, fetchMock);

    expect(body.based_on_revision_id).toBe(draft.id);
    expect("carry_forward_documents" in body).toBe(false);
  });

  it("sends carry forward false when the user unchecks it", async () => {
    const fetchMock = mockCreated();
    const user = await openForm([sampleRevision]);
    await user.click(carryBox());

    const body = await submit(user, fetchMock);

    expect("based_on_revision_id" in body).toBe(false);
    expect(body.carry_forward_documents).toBe(false);
  });

  it("resets carry forward to its default when the base changes", async () => {
    const user = await openForm([sampleRevision, draft]);
    await user.click(carryBox());
    expect(carryBox()).not.toBeChecked();

    await user.selectOptions(baseSelect(), "Revision REV-2 (Draft)");

    expect(carryBox()).toBeChecked();
  });

  it("reports how many documents were carried forward", async () => {
    const fetchMock = mockCreated({ inherited_document_count: 3 });
    const user = await openForm([sampleRevision]);

    await submit(user, fetchMock);

    await waitFor(() => {
      expect(
        screen.getByText("Revision REV-3 created. 3 documents carried forward."),
      ).toBeInTheDocument();
    });
  });

  it("uses the singular for one document and no count for none", async () => {
    const one = mockCreated({ inherited_document_count: 1 });
    const user = await openForm([sampleRevision]);
    await submit(user, one);
    await waitFor(() => {
      expect(screen.getByText("Revision REV-3 created. 1 document carried forward.")).toBeInTheDocument();
    });
  });

  it("shows no count when nothing was carried forward", async () => {
    const fetchMock = mockCreated({ inherited_document_count: 0 });
    const user = await openForm([sampleRevision]);
    await submit(user, fetchMock);
    await waitFor(() => {
      expect(screen.getByText("Revision REV-3 created.")).toBeInTheDocument();
    });
  });

  it("shows the lineage in the revision list", () => {
    render(
      <ProjectDetail
        initialProject={sampleProject}
        initialRevisions={[
          { ...draft, based_on_revision_id: sampleRevision.id, based_on_identifier: "REV-1" },
          sampleRevision,
        ]}
      />,
    );

    expect(screen.getByText(/Based on/)).toHaveTextContent("Based on Revision REV-1");
    expect(screen.getAllByText(/Based on/)).toHaveLength(1);
  });
});
