import { describe, expect, it } from "vitest";

import {
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
