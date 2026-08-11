import { useEffect, useState } from "react";
import { api } from "../api/client";

export interface HealthState {
  status: "loading" | "ok" | "error";
  liveModel: boolean;
  llm: string | null;
}

const INITIAL: HealthState = { status: "loading", liveModel: false, llm: null };

/** Reads `/api/health` once on mount. */
export function useHealth(): HealthState {
  const [health, setHealth] = useState<HealthState>(INITIAL);

  useEffect(() => {
    let cancelled = false;
    api
      .health()
      .then((payload) => {
        if (cancelled) return;
        setHealth({
          status: "ok",
          liveModel: payload.live_model,
          llm: payload.llm,
        });
      })
      .catch(() => {
        if (!cancelled) setHealth({ ...INITIAL, status: "error" });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return health;
}
