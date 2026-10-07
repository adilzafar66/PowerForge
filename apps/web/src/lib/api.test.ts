import { afterEach, describe, expect, it, vi } from "vitest";

import { apiErrorOf, parseError, request } from "./api";

function failing(status: number, body: unknown, statusText = "Status Text"): Response {
  return {
    ok: false,
    status,
    statusText,
    json: async () => body,
  } as Response;
}

describe("parseError", () => {
  it("reads a plain string detail", async () => {
    expect(await parseError(failing(500, { detail: "boom" }))).toEqual({ detail: "boom" });
  });

  it("reads the structured detail and code", async () => {
    const error = await parseError(
      failing(409, { detail: { detail: "Removed", code: "document_removed" } }),
    );
    expect(error).toEqual({ detail: "Removed", code: "document_removed" });
  });

  it("keeps the existing association of a document_already_in_revision conflict", async () => {
    const error = await parseError(
      failing(409, {
        detail: {
          detail: "Restore it instead",
          code: "document_already_in_revision",
          existing_revision_document_id: "abc",
          existing_status: "REMOVED",
        },
      }),
    );
    expect(error).toEqual({
      detail: "Restore it instead",
      code: "document_already_in_revision",
      existing_revision_document_id: "abc",
      existing_status: "REMOVED",
    });
  });

  it("joins the messages of a 422 validation array", async () => {
    const error = await parseError(
      failing(422, { detail: [{ msg: "Field required" }, { msg: "Value is not valid" }] }),
    );
    expect(error.detail).toBe("Field required; Value is not valid");
    expect(error.code).toBeUndefined();
  });

  it("falls back to the status text for an empty array, unknown shape or non-JSON body", async () => {
    expect((await parseError(failing(422, { detail: [] }, "Unprocessable"))).detail).toBe(
      "Unprocessable",
    );
    expect((await parseError(failing(500, {}, "Server Error"))).detail).toBe("Server Error");
    const notJson = {
      ok: false,
      status: 502,
      statusText: "Bad Gateway",
      json: async () => {
        throw new Error("not json");
      },
    } as unknown as Response;
    expect((await parseError(notJson)).detail).toBe("Bad Gateway");
    expect((await parseError(failing(500, {}, ""))).detail).toBe("Request failed");
  });
});

describe("request", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("throws an error carrying the status and the parsed error", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      failing(409, { detail: { detail: "Conflict", code: "revision_read_only" } }),
    );

    const caught = await request("/api/x").catch((err: unknown) => err);

    expect(apiErrorOf(caught)).toMatchObject({
      status: 409,
      code: "revision_read_only",
      detail: "Conflict",
    });
  });

  it("sends JSON headers, no-store and returns undefined for 204", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue({ ok: true, status: 204 } as Response);

    expect(await request("/api/x", { method: "POST" })).toBeUndefined();

    const [url, init] = fetchMock.mock.calls[0]!;
    expect(String(url)).toMatch(/\/api\/x$/);
    expect(init?.cache).toBe("no-store");
    expect((init?.headers as Record<string, string>)["Content-Type"]).toBe("application/json");
  });
});

describe("apiErrorOf", () => {
  it("returns nulls for errors that did not come from the API", () => {
    expect(apiErrorOf(new Error("network down"))).toEqual({
      status: null,
      code: null,
      detail: "network down",
      error: null,
    });
    expect(apiErrorOf("weird").detail).toBe("Request failed");
  });
});
