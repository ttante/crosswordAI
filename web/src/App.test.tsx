import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { AppForTest } from "./App";
import type { ApiClientLike } from "./api/context";
import { runDetailFixture } from "./api/fixtures";

function fakeApi(overrides: Partial<ApiClientLike> = {}): ApiClientLike {
  return {
    createSourcePack: vi.fn(),
    generatePuzzle: vi.fn().mockResolvedValue(runDetailFixture),
    getRun: vi.fn(),
    listRuns: vi.fn(),
    getPlayerPuzzle: vi.fn(),
    getSourcePack: vi.fn(),
    ...overrides
  };
}

describe("App", () => {
  it("renders the creator studio dashboard route", () => {
    render(<AppForTest />);

    expect(screen.getByRole("heading", { name: "Dashboard" })).toBeInTheDocument();
    expect(screen.getByRole("navigation")).toBeInTheDocument();
    expect(screen.getByLabelText("Dashboard metrics")).toBeInTheDocument();
  });

  it("renders the create puzzle route", () => {
    render(<AppForTest initialEntries={["/create"]} />);

    expect(screen.getByRole("heading", { name: "Create Puzzle" })).toBeInTheDocument();
    expect(screen.getByLabelText("Create puzzle workflow")).toBeInTheDocument();
  });

  it("renders dynamic player routes with the light player theme", () => {
    const { container } = render(<AppForTest initialEntries={["/puzzles/puzzle_web_fixture"]} />);

    expect(screen.getByRole("heading", { name: "Puzzle Player" })).toBeInTheDocument();
    expect(container.querySelector(".app-shell")).toHaveAttribute("data-theme", "player");
  });

  it("renders all planned primary navigation links", () => {
    render(<AppForTest />);

    for (const name of ["Dashboard", "Create", "Runs", "Batches", "Experiments", "Registries", "Reports", "Admin"]) {
      expect(screen.getByRole("link", { name })).toBeInTheDocument();
    }
  });

  it("validates and submits the new puzzle workflow", async () => {
    const user = userEvent.setup();
    const api = fakeApi();
    render(<AppForTest initialEntries={["/create"]} apiClient={api} />);

    await user.click(screen.getByRole("button", { name: "Start Generation" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Theme is required.");

    await user.type(screen.getByLabelText("Theme"), "Miles Davis");
    await user.type(screen.getByLabelText("Source notes"), "Miles Davis recorded Kind of Blue with John Coltrane.");
    await user.selectOptions(screen.getByLabelText("Model route"), "cheap_first_cascade");
    await user.click(screen.getByRole("radio", { name: "trivia" }));
    await user.click(screen.getByRole("button", { name: "Start Generation" }));

    expect(api.generatePuzzle).toHaveBeenCalledWith({
      theme: "Miles Davis",
      notes: "Miles Davis recorded Kind of Blue with John Coltrane.",
      route_id: "cheap_first_cascade",
      puzzle_id: "puzzle_miles-davis",
      grid_size: 5,
      clue_styles: ["trivia"],
      candidate_limit: 25
    });
    expect(await screen.findByLabelText("Generation started")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open run" })).toHaveAttribute("href", "/runs/run_web_fixture");
  });
});
