import { createContext, useContext, type ReactNode } from "react";
import { useLiveWorld, type LiveWorldState } from "@saathi/api-client";

/** One event stream for the whole control centre, shared by every section. */
const WorldContext = createContext<LiveWorldState | null>(null);

export function WorldProvider({ children }: { children: ReactNode }) {
  const world = useLiveWorld();
  return <WorldContext.Provider value={world}>{children}</WorldContext.Provider>;
}

export function useWorld(): LiveWorldState {
  const world = useContext(WorldContext);
  if (!world) throw new Error("useWorld outside WorldProvider");
  return world;
}
