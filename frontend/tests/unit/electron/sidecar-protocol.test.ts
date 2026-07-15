// @vitest-environment node

import { expect, it } from "vitest";

import { connectionFromReady, parseReadyFrame, READY_PREFIX } from "../../../electron/sidecar-protocol";

it("accepts a bounded loopback ready frame without exposing the token in the frame", () => {
  const line =
    READY_PREFIX +
    JSON.stringify({
      protocol_version: 1,
      status: "ready",
      host: "127.0.0.1",
      port: 54321,
      pid: 1234,
    });
  const frame = parseReadyFrame(line);
  const connection = connectionFromReady(frame, "temporary-session-secret");

  expect(frame).not.toHaveProperty("session_token");
  expect(connection.origin).toBe("http://127.0.0.1:54321");
  expect(connection.sessionToken).toBe("temporary-session-secret");
});

it("rejects non-loopback, invalid and oversized ready frames", () => {
  expect(() => parseReadyFrame("ordinary log line")).toThrow("invalid ready");
  expect(() =>
    parseReadyFrame(
      READY_PREFIX +
        JSON.stringify({
          protocol_version: 1,
          status: "ready",
          host: "0.0.0.0",
          port: 54321,
          pid: 1234,
        }),
    ),
  ).toThrow("protocol v1");
  expect(() => parseReadyFrame(READY_PREFIX + "x".repeat(5000))).toThrow("invalid ready");
});

