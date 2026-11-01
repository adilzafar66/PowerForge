import { describe, expect, it } from "vitest";
import { cn } from "./utils";

describe("semantic Tailwind utility composition", () => {
  it("keeps font size and color independent across component overrides", () => {
    const classes = cn(
      "text-workspace-body text-ink",
      "text-workspace-label text-muted",
    ).split(" ");
    expect(classes).toContain("text-workspace-label");
    expect(classes).toContain("text-muted");
    expect(classes).not.toContain("text-workspace-body");
    expect(classes).not.toContain("text-ink");
  });
  it("replaces the default shadow with a workspace elevation", () => {
    expect(cn("shadow-xl", "shadow-workspace-drawer")).toBe(
      "shadow-workspace-drawer",
    );
  });
  it("retains explicit line height after choosing a typography variant", () => {
    expect(
      cn(
        "text-workspace-caption",
        "text-workspace-label",
        "leading-[var(--pf-leading-copy)]",
      ),
    ).toContain("leading-[var(--pf-leading-copy)]");
  });
});
