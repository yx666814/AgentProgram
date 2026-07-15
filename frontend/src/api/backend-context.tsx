import {
  createContext,
  type PropsWithChildren,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

import type { DesktopPort } from "../../electron/desktop-port";
import { EventStream } from "../events/event-stream";
import { createEventReadModel, type EventReadModel } from "../events/event-reducer";
import { BackendApi } from "./backend-api";

interface BackendContextValue {
  api: BackendApi | null;
  events: EventReadModel;
  port: DesktopPort | null;
}

const disconnectedBackend: BackendContextValue = {
  api: null,
  events: createEventReadModel(),
  port: null,
};

const BackendContext = createContext<BackendContextValue>(disconnectedBackend);

export type BackendProviderProps = PropsWithChildren<{
  port?: DesktopPort | null;
}>;

function readDesktopPort(): DesktopPort | null {
  const desktop: unknown = Reflect.get(window, "desktop");
  return desktop === undefined ? null : (desktop as DesktopPort);
}

export function BackendProvider({ children, port }: BackendProviderProps) {
  const resolvedPort = port === undefined ? readDesktopPort() : port;
  const api = useMemo(() => (resolvedPort === null ? null : new BackendApi(resolvedPort)), [resolvedPort]);
  const [events, setEvents] = useState<EventReadModel>(() => createEventReadModel());

  useEffect(() => {
    if (resolvedPort === null) {
      setEvents(createEventReadModel());
      return;
    }
    const stream = new EventStream(resolvedPort, setEvents);
    stream.start();
    void stream.requestReplay().catch(() => {
      // Connection errors are rendered by query surfaces; the renderer never fabricates events.
    });
    return () => {
      stream.stop();
    };
  }, [resolvedPort]);

  const value = useMemo<BackendContextValue>(
    () => ({ api, events, port: resolvedPort }),
    [api, events, resolvedPort],
  );

  return <BackendContext.Provider value={value}>{children}</BackendContext.Provider>;
}

export function useBackend(): BackendContextValue {
  return useContext(BackendContext);
}
