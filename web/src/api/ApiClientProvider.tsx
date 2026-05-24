import type { ReactNode } from "react";

import { apiClient } from "./client";
import { ApiClientContext, type ApiClientLike } from "./context";

export function ApiClientProvider({ children, client }: { children: ReactNode; client?: ApiClientLike }) {
  return <ApiClientContext.Provider value={client ?? apiClient}>{children}</ApiClientContext.Provider>;
}
