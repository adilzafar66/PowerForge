/** @vitest-environment jsdom */
import React from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ReadOnlyBanner } from "@/components/read-only-banner";
import type { ProjectStatus, RevisionStatus } from "@/lib/projects";

function renderBanner(project: ProjectStatus, revision: RevisionStatus) {
  return render(<ReadOnlyBanner project={{ status: project }} revision={{ status: revision }} />);
}

describe("ReadOnlyBanner", () => {
  it.each([
    ["ACTIVE", "SUPERSEDED", /revision is superseded/],
    ["ARCHIVED", "ACTIVE", /project is archived/],
    ["CANCELLED", "DRAFT", /project is cancelled/],
  ] as const)("is shown for project %s with revision %s", (project, revision, text) => {
    renderBanner(project, revision);
    expect(screen.getByRole("status")).toHaveTextContent(text);
    expect(screen.getByRole("status")).toHaveTextContent(/downloaded/);
  });

  it.each([
    ["ACTIVE", "DRAFT"],
    ["ACTIVE", "ACTIVE"],
    ["PAUSED", "ACTIVE"],
    ["PAUSED", "DRAFT"],
  ] as const)("is hidden for project %s with revision %s", (project, revision) => {
    const { container } = renderBanner(project, revision);
    expect(container).toBeEmptyDOMElement();
  });
});
