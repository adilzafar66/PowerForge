import { useState } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { DocumentFiltersPopover } from "./document-workspace-toolbar";
import { EMPTY_ADVANCED_FILTERS } from "@/lib/document-presentation";

function Filters() {
  const [filters, setFilters] = useState(EMPTY_ADVANCED_FILTERS);
  return (
    <>
      <DocumentFiltersPopover filters={filters} onChange={setFilters} />
      <output aria-label="Origin value">{filters.origin}</output>
      <button>Outside</button>
    </>
  );
}

describe("document filters with portalled selects", () => {
  it("keeps the popover mounted through mouse-down and option selection", async () => {
    const user = userEvent.setup();
    render(<Filters />);
    await user.click(screen.getByRole("button", { name: "Filters" }));
    const filtersDialog = screen.getByRole("dialog", { name: "Filters" });
    await user.click(screen.getByLabelText("Origin"));
    const option = screen.getByRole("option", { name: "Inherited" });
    fireEvent.mouseDown(option);
    expect(filtersDialog).toBeInTheDocument();
    await user.click(option);
    expect(screen.getByLabelText("Origin value")).toHaveTextContent(
      "INHERITED",
    );
    expect(screen.getByRole("dialog", { name: "Filters" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Outside" }));
    expect(
      screen.queryByRole("dialog", { name: "Filters" }),
    ).not.toBeInTheDocument();
  });
  it("supports keyboard choice and dismisses the select before the filters", async () => {
    const user = userEvent.setup();
    render(<Filters />);
    await user.click(screen.getByRole("button", { name: "Filters" }));
    screen.getByLabelText("Origin").focus();
    await user.keyboard("{ArrowDown}{End}{Enter}");
    expect(screen.getByLabelText("Origin value")).toHaveTextContent(
      "INHERITED",
    );
    await user.keyboard("{ArrowDown}{Escape}");
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
    expect(screen.getByRole("dialog", { name: "Filters" })).toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(
      screen.queryByRole("dialog", { name: "Filters" }),
    ).not.toBeInTheDocument();
  });
});
