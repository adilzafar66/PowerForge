import { act, render, screen, waitFor } from "@/components/query-test-utils";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { RevisionEditor, positiveDecimal } from "./revision-editor";
import { ProjectDetail } from "./project-detail";
import { RevisionOverview } from "./revision-overview";
import { keys } from "@/lib/query-keys";
import { selectOption } from "@/components/ui/control-test-helpers";
import type { Project, Revision } from "@/lib/projects";

const nav = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => nav }));
const project: Project = {
  id: "p",
  project_number: "P1",
  project_name: "Station",
  project_address: null,
  project_scope: null,
  client_name: null,
  description: null,
  engineer_names: [],
  status: "ACTIVE",
  created_at: "2026-01-01",
  updated_at: "2026-01-01",
  archived_at: null,
  status_before_archive: null,
  created_by: null,
  active_revision_identifier: "A",
};
const revision: Revision = {
  id: "r",
  project_id: "p",
  identifier: "A",
  description: "Original",
  status: "ACTIVE",
  created_at: "2026-01-01",
  updated_at: "2026-01-01",
  created_by: null,
  based_on_revision_id: null,
  based_on_identifier: null,
  system_frequency: "60",
  system_phase_count: 3,
};
afterEach(() => {
  vi.restoreAllMocks();
  nav.push.mockReset();
});
const response = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), { status });

describe("revision editing", () => {
  it("sends exact decimal strings, explicit null clears, and omits unchanged fields", async () => {
    const fetch = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(response(revision));
    const user = userEvent.setup(),
      saved = vi.fn();
    render(
      <RevisionEditor
        project={project}
        revision={revision}
        onClose={vi.fn()}
        onSaved={saved}
      />,
    );
    const frequency = screen.getByLabelText("System frequency (Hz)");
    await user.clear(frequency);
    await user.type(frequency, "60.12345678901234567890123456789");
    await selectOption(screen.getByLabelText("System phase count"), "Not set");
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(saved).toHaveBeenCalled());
    expect(JSON.parse(String(fetch.mock.calls[0][1]?.body))).toEqual({
      system_frequency: "60.12345678901234567890123456789",
      system_phase_count: null,
    });
    expect(fetch.mock.calls[0][1]?.method).toBe("PATCH");
  });
  it("clears frequency explicitly and keeps a failed draft available for retry", async () => {
    const fetch = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(response({ detail: "Permission changed" }, 409));
    const user = userEvent.setup();
    render(
      <RevisionEditor
        project={project}
        revision={revision}
        onClose={vi.fn()}
        onSaved={vi.fn()}
      />,
    );
    await user.clear(screen.getByLabelText("System frequency (Hz)"));
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Permission changed",
    );
    expect(JSON.parse(String(fetch.mock.calls[0][1]?.body))).toEqual({
      system_frequency: null,
    });
    expect(screen.getByLabelText("System frequency (Hz)")).toHaveValue("");
  });
  it("allows descriptive edits on superseded revisions without sending engineering settings", async () => {
    const fetch = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(
        response({ detail: "Identifier already exists" }, 409),
      );
    const user = userEvent.setup();
    render(
      <RevisionEditor
        project={{ ...project, status: "PAUSED" }}
        revision={{ ...revision, status: "SUPERSEDED" }}
        onClose={vi.fn()}
        onSaved={vi.fn()}
      />,
    );
    expect(screen.getByLabelText("System frequency (Hz)")).toBeDisabled();
    expect(screen.getByLabelText("System phase count")).toBeDisabled();
    await user.clear(screen.getByLabelText(/Revision Identifier/));
    await user.type(screen.getByLabelText(/Revision Identifier/), "B");
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Identifier already exists",
    );
    expect(JSON.parse(String(fetch.mock.calls[0][1]?.body))).toEqual({
      identifier: "B",
    });
  });
  it.each(["0", "-1", "NaN", "Infinity", "0e100", "abc"])(
    "rejects invalid frequency %s",
    async (value) => {
      expect(positiveDecimal(value)).toBe(false);
      const user = userEvent.setup();
      render(
        <RevisionEditor
          project={project}
          revision={revision}
          onClose={vi.fn()}
          onSaved={vi.fn()}
        />,
      );
      await user.clear(screen.getByLabelText("System frequency (Hz)"));
      await user.type(screen.getByLabelText("System frequency (Hz)"), value);
      expect(
        screen.getByRole("button", { name: "Save changes" }),
      ).toBeDisabled();
    },
  );
  it("preserves a revision draft across new server props and protects discard", async () => {
    const close = vi.fn(),
      user = userEvent.setup();
    const view = render(
      <RevisionEditor
        project={project}
        revision={revision}
        onClose={close}
        onSaved={vi.fn()}
      />,
    );
    await user.type(screen.getByLabelText("Description"), " draft");
    view.rerender(
      <RevisionEditor
        project={project}
        revision={{ ...revision, description: "Background refresh" }}
        onClose={close}
        onSaved={vi.fn()}
      />,
    );
    expect(screen.getByLabelText("Description")).toHaveValue("Original draft");
    await user.keyboard("{Escape}");
    expect(close).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Discard changes" }));
    expect(close).toHaveBeenCalledOnce();
  });
  it.each(["ARCHIVED", "CANCELLED"] as const)(
    "locks all edits for %s projects",
    (status) => {
      render(
        <RevisionEditor
          project={{ ...project, status }}
          revision={revision}
          onClose={vi.fn()}
          onSaved={vi.fn()}
        />,
      );
      expect(screen.getByLabelText(/Revision Identifier/)).toBeDisabled();
      expect(
        screen.getByRole("button", { name: "Save changes" }),
      ).toBeDisabled();
    },
  );
});

describe("project and revision workspaces", () => {
  it("keeps a project draft through refetch and saves only changed metadata", async () => {
    const fetch = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(
        response({ ...project, project_name: "Station revised" }),
      );
    const user = userEvent.setup();
    const { queryClient } = render(
      <ProjectDetail initialProject={project} initialRevisions={[revision]} />,
    );
    await user.click(screen.getByRole("button", { name: "Edit details" }));
    await user.type(screen.getByLabelText(/Project Name/), " revised");
    act(() =>
      queryClient.setQueryData(keys.project("p"), {
        ...project,
        project_name: "Background name",
      }),
    );
    expect(screen.getByLabelText(/Project Name/)).toHaveValue(
      "Station revised",
    );
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(
      screen.getByRole("dialog", { name: "Discard unsaved changes?" }),
    ).toBeInTheDocument();
    await user.keyboard("{Escape}");
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByText("Project updated.")).toBeInTheDocument();
    expect(JSON.parse(String(fetch.mock.calls[0][1]?.body))).toEqual({
      project_name: "Station revised",
    });
    expect(
      screen.getByRole("heading", { name: "Station revised" }),
    ).toBeInTheDocument();
  });
  it("provides a filtered revision register with keyboard links and preserves filters on refresh", async () => {
    const user = userEvent.setup();
    const draft = {
      ...revision,
      id: "new",
      identifier: "B",
      description: "New design",
      status: "DRAFT" as const,
    };
    const { queryClient } = render(
      <ProjectDetail
        initialProject={project}
        initialRevisions={[revision, draft]}
        revisionsPage
      />,
    );
    await user.type(screen.getByLabelText("Search revisions"), "design");
    expect(screen.queryByRole("link", { name: "A" })).not.toBeInTheDocument();
    const link = screen.getByRole("link", { name: "B" });
    expect(link).toHaveAttribute(
      "href",
      "/projects/p/revisions/new?view=overview",
    );
    act(() =>
      queryClient.setQueryData(keys.revisions("p"), [
        revision,
        { ...draft, description: "New design refreshed" },
      ]),
    );
    expect(screen.getByLabelText("Search revisions")).toHaveValue("design");
    expect(await screen.findByText("New design refreshed")).toBeInTheDocument();
    expect(
      screen.queryByRole("columnheader", { name: "Actions" }),
    ).not.toBeInTheDocument();
  });
  it("does not offer activation of an older draft", () => {
    render(
      <RevisionOverview
        project={project}
        revision={{
          ...revision,
          id: "old",
          status: "DRAFT",
          created_at: "2025-01-01",
        }}
        revisions={[revision]}
      />,
    );
    expect(
      screen.getByRole("button", { name: "Activate revision" }),
    ).toBeDisabled();
  });
  it("does not supersede the active revision on activation failure", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      response({ detail: "Activation refused" }, 409),
    );
    const user = userEvent.setup();
    const draft = {
      ...revision,
      id: "new",
      status: "DRAFT" as const,
      created_at: "2026-02-01",
    };
    const { queryClient } = render(
      <RevisionOverview
        project={project}
        revision={draft}
        revisions={[revision, draft]}
      />,
    );
    queryClient.setQueryDefaults(keys.revisions("p"), { gcTime: Infinity });
    queryClient.setQueryData(keys.revisions("p"), [revision, draft]);
    await user.click(screen.getByRole("button", { name: "Activate revision" }));
    await user.click(screen.getByRole("button", { name: "Activate" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Activation refused",
    );
    expect(
      queryClient.getQueryData<Revision[]>(keys.revisions("p"))?.[0].status,
    ).toBe("ACTIVE");
  });
});
