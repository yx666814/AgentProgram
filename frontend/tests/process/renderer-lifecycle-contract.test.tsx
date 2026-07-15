import { render } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import type { DesktopPort } from "../../electron/desktop-port";
import { BackendProvider } from "../../src/api/backend-context";

it("subscribes, replays from zero and releases the renderer event listener on unmount", () => {
  const unsubscribe = vi.fn();
  const subscribe = vi.fn(() => unsubscribe);
  const requestReplay = vi.fn(() => Promise.resolve());
  const port = {
    backend: { query: vi.fn(), command: vi.fn(), subscribe, requestReplay },
  } as unknown as DesktopPort;

  const rendered = render(<BackendProvider port={port}><div>child</div></BackendProvider>);
  expect(subscribe).toHaveBeenCalledOnce();
  expect(requestReplay).toHaveBeenCalledWith(0);
  rendered.unmount();
  expect(unsubscribe).toHaveBeenCalledOnce();
});
