import { createContext, useContext } from "react";

import { CrosswordApiClient, apiClient } from "./client";

export type ApiClientLike = Pick<
  CrosswordApiClient,
  "createSourcePack" | "generatePuzzle" | "getRun" | "listRuns" | "getPlayerPuzzle" | "getSourcePack"
>;

export const ApiClientContext = createContext<ApiClientLike>(apiClient);

export function useApiClient(): ApiClientLike {
  return useContext(ApiClientContext);
}
