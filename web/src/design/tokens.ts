export type ThemeName = "studio" | "player";
export type StatusName = "succeeded" | "running" | "failed" | "quarantined" | "pending" | "warning";

export const themeTokens = {
  studio: {
    colorScheme: "dark",
    background: "var(--color-bg)",
    surface: "var(--color-surface)",
    text: "var(--color-text)",
    accent: "var(--color-accent)"
  },
  player: {
    colorScheme: "light",
    background: "var(--player-bg)",
    surface: "var(--player-surface)",
    text: "var(--player-text)",
    accent: "var(--player-accent)"
  }
} as const satisfies Record<ThemeName, Record<string, string>>;

export const statusTokens = {
  succeeded: "var(--status-succeeded)",
  running: "var(--status-running)",
  failed: "var(--status-failed)",
  quarantined: "var(--status-quarantined)",
  pending: "var(--status-pending)",
  warning: "var(--status-warning)"
} as const satisfies Record<StatusName, string>;

export const boardTokens = {
  minCellSize: "var(--board-cell-min)",
  maxCellSize: "var(--board-cell-max)",
  blockColor: "var(--board-block)",
  activeCellColor: "var(--board-active-cell)",
  activeEntryColor: "var(--board-active-entry)",
  borderColor: "var(--board-border)"
} as const;

export const focusToken = "var(--focus-ring)";

export function themeAttribute(theme: ThemeName): { "data-theme": ThemeName } {
  return { "data-theme": theme };
}
