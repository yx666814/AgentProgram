import { EventEmitter } from "node:events";
import { PassThrough } from "node:stream";

import { afterEach, describe, expect, it, vi } from "vitest";

const spawnMock = vi.hoisted(() => vi.fn());

vi.mock("node:child_process", () => ({
  default: { spawn: spawnMock },
  spawn: spawnMock,
}));

vi.mock("electron", () => ({
  app: {
    getAppPath: () => "D:\\AgentProgram\\frontend",
    getPath: () => "D:\\AgentProgram\\data",
    isPackaged: false,
  },
}));

import { SidecarManager } from "../../../electron/sidecar";
import { READY_PREFIX } from "../../../electron/sidecar-protocol";

class FakeChild extends EventEmitter {
  readonly stdin = new PassThrough();
  readonly stdout = new PassThrough();
  readonly stderr = new PassThrough();
  exitCode: number | null = null;
  signalCode: NodeJS.Signals | null = null;
  readonly kill = vi.fn(() => true);

  constructor(readonly pid: number) {
    super();
  }
}

function emitReady(child: FakeChild, port: number): void {
  child.stdout.write(
    `${READY_PREFIX}${JSON.stringify({
      protocol_version: 1,
      status: "ready",
      host: "127.0.0.1",
      port,
      pid: child.pid,
    })}\n`,
  );
}

describe("SidecarManager", () => {
  afterEach(() => {
    spawnMock.mockReset();
  });

  it("restarts after startup failure and after a ready child exits", async () => {
    const failed = new FakeChild(101);
    const ready = new FakeChild(102);
    const replacement = new FakeChild(103);
    spawnMock
      .mockReturnValueOnce(failed)
      .mockReturnValueOnce(ready)
      .mockReturnValueOnce(replacement);
    const manager = new SidecarManager({
      origin: "http://127.0.0.1:54321",
      token: "bridge-token",
    });

    const firstStartup = manager.start();
    const firstOutcome = firstStartup.then(
      () => null,
      (error: unknown) => error,
    );
    failed.exitCode = 1;
    failed.emit("exit", 1, null);
    await expect(firstOutcome).resolves.toMatchObject({
      message: "Sidecar exited before ready (code=1, signal=null)",
    });

    const secondStartup = manager.start();
    emitReady(ready, 43101);
    await expect(secondStartup).resolves.toMatchObject({ port: 43101, pid: 102 });

    ready.exitCode = 1;
    ready.emit("exit", 1, null);
    const thirdStartup = manager.connection();
    emitReady(replacement, 43102);
    await expect(thirdStartup).resolves.toMatchObject({ port: 43102, pid: 103 });
    expect(spawnMock).toHaveBeenCalledTimes(3);

    replacement.exitCode = 0;
    replacement.emit("exit", 0, null);
  });
});
