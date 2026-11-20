import { afterEach, expect, it, vi } from "vitest";
import { getGroupCandidates } from "./extraction";

afterEach(() => vi.unstubAllGlobals());

it("reads integer proposals beyond Number precision without changing other primitives", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(
    '{"items":[{"proposed_value":9007199254740993},{"proposed_value":7},' +
    '{"proposed_value":false},{"proposed_value":"015.750"},{"proposed_value":null}]}',
  )));
  const candidates = await getGroupCandidates(
    { projectId: "project", revisionId: "revision", documentId: "document" },
    "run", "group", {}, null,
  );
  expect(candidates.items).toEqual([
    { proposed_value: BigInt("9007199254740993") }, { proposed_value: 7 },
    { proposed_value: false }, { proposed_value: "015.750" }, { proposed_value: null },
  ]);
});
