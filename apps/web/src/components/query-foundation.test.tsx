/** @vitest-environment jsdom */
import { useEffect } from "react";
import { QueryClient, useQueryClient } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@/components/query-test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import { QueryProvider } from "./query-provider";
import { AsyncState } from "./ui/async-state";
import { useResource } from "@/lib/query-hooks";
import { keys } from "@/lib/query-keys";
import { invalidateWrite } from "@/lib/query-client";
import { request } from "@/lib/api";

afterEach(() => vi.restoreAllMocks());

describe("shared server state", () => {
  it("retains data on a failed background refresh and recovers without losing local context", async () => {
    const load = vi.fn().mockResolvedValue("Original");
    function View() {
      const q = useResource<string>(["sample"], load);
      return (
        <>
          <span>{q.data}</span>
          <AsyncState
            pending={q.loading}
            refreshing={q.refreshing}
            error={q.error ? new Error(q.error) : null}
            retry={q.retry}
          />
        </>
      );
    }
    const { queryClient } = render(<View />);
    await screen.findByText("Original");
    load.mockRejectedValue(new Error("Service unavailable"));
    await act(() => queryClient.invalidateQueries({ queryKey: ["sample"] }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Service unavailable",
    );
    expect(screen.getByText("Original")).toBeInTheDocument();
    load.mockResolvedValue("Fresh");
    await act(() => queryClient.refetchQueries({ queryKey: ["sample"] }));
    await screen.findByText("Fresh");
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("isolates late responses by revision identity", async () => {
    let finish!: (value: string) => void;
    const old = new Promise<string>((resolve) => {
      finish = resolve;
    });
    function View({ revision }: { revision: string }) {
      const q = useResource(["revision-data", revision], () =>
        revision === "old" ? old : Promise.resolve("Current revision"),
      );
      return <span>{q.data}</span>;
    }
    const view = render(<View revision="old" />);
    view.rerender(<View revision="new" />);
    await screen.findByText("Current revision");
    await act(async () => finish("Old revision"));
    expect(screen.queryByText("Old revision")).toBeNull();
  });

  it("invalidates equipment dependencies within only the affected revision", async () => {
    const client = new QueryClient();
    const affected = [
      keys.equipment("p", "r"),
      keys.editor("p", "r", "e"),
      keys.nodes("p", "r"),
      keys.connections("p", "r"),
    ];
    const untouched = [
      keys.equipment("p", "other"),
      keys.documentList("p", "r", ""),
      keys.registry,
      keys.editor("p", "r", "another"),
    ];
    for (const key of [...affected, ...untouched]) client.setQueryData(key, []);
    await invalidateWrite(
      client,
      "/api/projects/p/revisions/r/equipment/e/editor",
    );
    for (const key of affected)
      expect(client.getQueryState(key)?.isInvalidated).toBe(true);
    for (const key of untouched)
      expect(client.getQueryState(key)?.isInvalidated).toBe(false);
    client.clear();
  });

  it("activation refreshes labels for the project and its revisions without refreshing unrelated models", async () => {
    const client = new QueryClient();
    const affected = [
      keys.projects,
      keys.project("p"),
      keys.revisions("p"),
      keys.revision("p", "old"),
      keys.revision("p", "new"),
    ];
    const untouched = [keys.project("other"), keys.nodes("p", "new")];
    for (const key of [...affected, ...untouched]) client.setQueryData(key, []);
    await invalidateWrite(client, "/api/projects/p/revisions/new/activate");
    affected.forEach((key) =>
      expect(client.getQueryState(key)?.isInvalidated).toBe(true),
    );
    untouched.forEach((key) =>
      expect(client.getQueryState(key)?.isInvalidated).toBe(false),
    );
    client.clear();
  });

  it("the production provider invalidates only after backend confirmation, never after failure", async () => {
    let client!: QueryClient;
    function Probe() {
      const current = useQueryClient();
      useEffect(() => {
        client = current;
      }, [current]);
      return null;
    }
    render(
      <QueryProvider>
        <Probe />
      </QueryProvider>,
    );
    const key = keys.connections("p", "r");
    client.setQueryData(key, []);
    let finish!: (response: Response) => void;
    vi.spyOn(globalThis, "fetch").mockImplementation(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    );
    const save = request("/api/projects/p/revisions/r/connections/c", {
      method: "PATCH",
      body: "{}",
    });
    expect(client.getQueryState(key)?.isInvalidated).toBe(false);
    finish(new Response("{}", { status: 200 }));
    await save;
    await waitFor(() =>
      expect(client.getQueryState(key)?.isInvalidated).toBe(true),
    );
    client.setQueryData(key, []);
    const failure = request("/api/projects/p/revisions/r/connections/c", {
      method: "PATCH",
      body: "{}",
    });
    finish(
      new Response(
        JSON.stringify({
          detail: { code: "revision_read_only", detail: "Read only" },
        }),
        { status: 409 },
      ),
    );
    await expect(failure).rejects.toMatchObject({
      status: 409,
      apiError: { code: "revision_read_only" },
    });
    expect(client.getQueryState(key)?.isInvalidated).toBe(false);
  });
});
