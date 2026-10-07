import { afterEach, describe, expect, it, vi } from "vitest";

import {
  createRevision,
  formatDate,
  parseEngineerNames,
  projectStatusBadgeVariant,
  revisionStatusBadgeVariant,
} from "./projects";

describe("projects helpers", () => {
  it("parses comma-separated engineer names", () => {
    expect(parseEngineerNames("Ada Lovelace,  Grace Hopper,")).toEqual([
      "Ada Lovelace",
      "Grace Hopper",
    ]);
    expect(parseEngineerNames("")).toEqual([]);
  });

  it("maps status badges", () => {
    expect(projectStatusBadgeVariant("ACTIVE")).toBe("active");
    expect(projectStatusBadgeVariant("ARCHIVED")).toBe("archived");
    expect(revisionStatusBadgeVariant("DRAFT")).toBe("draft");
    expect(revisionStatusBadgeVariant("SUPERSEDED")).toBe("superseded");
  });

  it("formats dates stably in UTC", () => {
    expect(formatDate("2026-09-04T06:18:25.000Z")).toBe("2026-09-04, 06:18:25");
    expect(formatDate(null)).toBe("—");
  });
});

describe("createRevision request body", () => {
  const PROJECT = "11111111-1111-1111-1111-111111111111";
  const BASE = "22222222-2222-2222-2222-222222222222";

  afterEach(() => {
    vi.restoreAllMocks();
  });

  async function bodyFor(input: Parameters<typeof createRevision>[1]) {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      status: 201,
      json: async () => ({ id: "x", inherited_document_count: 2 }),
    } as Response);
    const created = await createRevision(PROJECT, input);
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(String(url)).toMatch(new RegExp(`/api/projects/${PROJECT}/revisions$`));
    expect(init?.method).toBe("POST");
    return { created, body: JSON.parse(String(init?.body)) as Record<string, unknown> };
  }

  it("omits the base and carry-forward keys by default", async () => {
    const { body, created } = await bodyFor({ identifier: "2", description: null, activate: false });
    expect(body).toEqual({ identifier: "2", description: null, activate: false });
    expect("based_on_revision_id" in body).toBe(false);
    expect("carry_forward_documents" in body).toBe(false);
    expect(created.inherited_document_count).toBe(2);
  });

  it("sends an explicit null for no base, which differs from omitting it", async () => {
    const { body } = await bodyFor({
      identifier: "2",
      based_on_revision_id: null,
      carry_forward_documents: false,
    });
    expect(body.based_on_revision_id).toBeNull();
    expect(body.carry_forward_documents).toBe(false);
  });

  it("sends an explicit base, and carry forward turned off", async () => {
    const { body } = await bodyFor({
      identifier: "2",
      based_on_revision_id: BASE,
      carry_forward_documents: false,
    });
    expect(body.based_on_revision_id).toBe(BASE);
    expect(body.carry_forward_documents).toBe(false);
  });
});
