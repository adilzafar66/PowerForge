import { describe, expect, it } from "vitest";
import { revisionHref } from "./workspace-navigation";

describe("revision navigation", () => {
  it("keeps unrelated parameters and current equipment selection", () => {
    expect(
      revisionHref(
        "p",
        "r",
        "r",
        "search=bus&equipment=e&document=d",
        "equipment",
      ),
    ).toBe(
      "/projects/p/revisions/r?search=bus&equipment=e&workspace=model&view=equipment",
    );
  });
  it("switches revision with the same workspace but no stale object IDs", () => {
    expect(
      revisionHref(
        "p",
        "next",
        "r",
        "workspace=model&view=topology&equipment=e&document=d&search=bus",
      ),
    ).toBe(
      "/projects/p/revisions/next?workspace=model&view=topology&search=bus",
    );
  });
  it("maps overview, documents and topology to working existing routes", () => {
    const old =
      "workspace=model&view=equipment&equipment=e&document=d&filter=active";
    expect(revisionHref("p", "r", "r", old, "overview")).toBe(
      "/projects/p/revisions/r?view=overview&filter=active",
    );
    expect(revisionHref("p", "r", "r", old, "documents")).toBe(
      "/projects/p/revisions/r?document=d&filter=active",
    );
    expect(revisionHref("p", "r", "r", old, "topology")).toBe(
      "/projects/p/revisions/r?workspace=model&view=topology&filter=active",
    );
  });
});
