import { describe, expect, it } from "vitest";
import {
  documentViewerHref,
  equipmentTab,
  revisionHref,
} from "./workspace-navigation";

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
        "workspace=model&view=topology&equipment=e&document=d&node=n&connection=c&search=bus",
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
    expect(
      revisionHref(
        "p",
        "r",
        "r",
        "workspace=model&view=topology&node=n&connection=c&keep=yes",
        "equipment",
      ),
    ).toBe(
      "/projects/p/revisions/r?workspace=model&view=equipment&keep=yes",
    );
  });
  it("keeps editor state with its equipment and drops it with the selection", () => {
    const editing =
      "workspace=model&equipment=e&equipmentMode=edit&equipmentTab=terminals";
    expect(revisionHref("p", "r", "r", editing, "equipment")).toBe(
      "/projects/p/revisions/r?workspace=model&equipment=e&equipmentMode=edit&equipmentTab=terminals&view=equipment",
    );
    for (const href of [
      revisionHref("p", "next", "r", editing, "equipment"),
      revisionHref("p", "r", "r", editing, "topology"),
      revisionHref("p", "r", "r", editing, "documents"),
    ])
      expect(href).not.toMatch(/equipment(Mode|Tab)?=/);
  });
  it("defaults unknown editor tabs to General", () => {
    expect(equipmentTab("attributes")).toBe("attributes");
    expect(equipmentTab("other")).toBe("general");
    expect(equipmentTab(null)).toBe("general");
  });
});

describe("document viewer URLs", () => {
  it("keeps page 1 and document mode implicit", () => {
    expect(documentViewerHref("p", "r", "d")).toBe(
      "/projects/p/revisions/r/documents/d",
    );
    expect(documentViewerHref("p", "r", "d", { page: 1, mode: "document" })).toBe(
      "/projects/p/revisions/r/documents/d",
    );
    expect(documentViewerHref("p", "r", "d", { page: 4, mode: "evidence" })).toBe(
      "/projects/p/revisions/r/documents/d?page=4&mode=evidence",
    );
  });

  it("drops viewer-only state from revision links", () => {
    expect(
      revisionHref("p", "r", "r", "page=4&mode=evidence&keep=yes", "documents"),
    ).toBe("/projects/p/revisions/r?keep=yes");
  });
});
