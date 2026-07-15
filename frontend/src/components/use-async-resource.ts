import { useCallback, useEffect, useState } from "react";

export type AsyncResource<T> =
  | { phase: "loading"; data: null; error: null }
  | { phase: "ready"; data: T; error: null }
  | { phase: "error"; data: null; error: unknown };

export function useAsyncResource<T>(loader: () => Promise<T>): {
  resource: AsyncResource<T>;
  reload: () => Promise<void>;
} {
  const [resource, setResource] = useState<AsyncResource<T>>({
    phase: "loading",
    data: null,
    error: null,
  });

  const reload = useCallback(async () => {
    setResource({ phase: "loading", data: null, error: null });
    try {
      const data = await loader();
      setResource({ phase: "ready", data, error: null });
    } catch (error) {
      setResource({ phase: "error", data: null, error });
    }
  }, [loader]);

  useEffect(() => {
    void reload();
  }, [reload]);

  return { resource, reload };
}
