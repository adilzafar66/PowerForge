/** @vitest-environment jsdom */
import React from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

import { RevisionLineage } from "@/components/revision-lineage";

describe("RevisionLineage", () => {
  it("renders the base revision as plain text", () => {
    render(<RevisionLineage basedOnIdentifier="REV-1" />);
    expect(screen.getByText(/Based on/)).toHaveTextContent("Based on Revision REV-1");
    expect(screen.queryByRole("link")).toBeNull();
  });

  it("links to the base revision when an href is given", () => {
    render(<RevisionLineage basedOnIdentifier="REV-1" href="/projects/p/revisions/r" />);
    expect(screen.getByRole("link", { name: "Revision REV-1" })).toHaveAttribute(
      "href",
      "/projects/p/revisions/r",
    );
  });

  it("renders nothing without a base", () => {
    const { container } = render(<RevisionLineage basedOnIdentifier={null} />);
    expect(container).toBeEmptyDOMElement();
  });
});
