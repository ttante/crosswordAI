import { boardTokens, focusToken, statusTokens, themeAttribute, themeTokens } from "./tokens";

describe("design tokens", () => {
  it("defines split themes for studio and player surfaces", () => {
    expect(Object.keys(themeTokens)).toEqual(["studio", "player"]);
    expect(themeTokens.studio.colorScheme).toBe("dark");
    expect(themeTokens.player.colorScheme).toBe("light");
    expect(themeAttribute("player")).toEqual({ "data-theme": "player" });
  });

  it("covers operational statuses and board primitives", () => {
    expect(statusTokens).toMatchObject({
      succeeded: expect.stringContaining("--status-succeeded"),
      quarantined: expect.stringContaining("--status-quarantined"),
      failed: expect.stringContaining("--status-failed")
    });
    expect(boardTokens.minCellSize).toContain("--board-cell-min");
    expect(boardTokens.activeCellColor).toContain("--board-active-cell");
    expect(focusToken).toContain("--focus-ring");
  });
});
