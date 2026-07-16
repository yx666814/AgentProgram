import { createServer, type IncomingMessage, type Server, type ServerResponse } from "node:http";
import { timingSafeEqual, randomBytes } from "node:crypto";

import type { EncryptedSecretStore } from "./secret-store";
import { isRecord } from "./runtime-contracts";

const BODY_LIMIT = 1024;
const CREDENTIAL_REF_PATTERN = /^[a-z][a-z0-9_.:-]{2,127}$/;

export interface SecretBridgeConnection {
  origin: string;
  token: string;
}

function writeJson(response: ServerResponse, statusCode: number, payload: unknown): void {
  const body = JSON.stringify(payload);
  response.writeHead(statusCode, {
    "Cache-Control": "no-store",
    "Content-Type": "application/json; charset=utf-8",
    "Content-Length": Buffer.byteLength(body),
  });
  response.end(body);
}

function authorized(request: IncomingMessage, token: string): boolean {
  const value = request.headers.authorization;
  if (typeof value !== "string") {
    return false;
  }
  const expected = Buffer.from(`Bearer ${token}`);
  const actual = Buffer.from(value);
  return actual.length === expected.length && timingSafeEqual(actual, expected);
}

async function body(request: IncomingMessage): Promise<unknown> {
  const chunks: Buffer[] = [];
  let length = 0;
  for await (const chunk of request as AsyncIterable<Uint8Array>) {
    const bytes = Buffer.from(chunk);
    length += bytes.length;
    if (length > BODY_LIMIT) {
      throw new Error("Secret bridge request exceeded its size limit");
    }
    chunks.push(bytes);
  }
  return JSON.parse(Buffer.concat(chunks).toString("utf8"));
}

export class SecretBridgeServer {
  private server: Server | null = null;
  private connectionValue: SecretBridgeConnection | null = null;

  constructor(private readonly secrets: EncryptedSecretStore) {}

  async start(): Promise<SecretBridgeConnection> {
    if (this.connectionValue !== null) {
      return this.connectionValue;
    }
    const token = randomBytes(32).toString("base64url");
    const server = createServer((request, response) => {
      void this.handle(request, response, token);
    });
    await new Promise<void>((resolveListen, rejectListen) => {
      server.once("error", rejectListen);
      server.listen(0, "127.0.0.1", () => {
        server.off("error", rejectListen);
        resolveListen();
      });
    });
    const address = server.address();
    if (address === null || typeof address === "string" || address.address !== "127.0.0.1") {
      server.close();
      throw new Error("Secret bridge did not bind to an IPv4 loopback port");
    }
    this.server = server;
    this.connectionValue = {
      origin: `http://127.0.0.1:${String(address.port)}`,
      token,
    };
    return this.connectionValue;
  }

  async stop(): Promise<void> {
    const server = this.server;
    this.server = null;
    this.connectionValue = null;
    if (server === null) {
      return;
    }
    await new Promise<void>((resolveClose) => {
      server.close(() => {
        resolveClose();
      });
    });
  }

  private async handle(
    request: IncomingMessage,
    response: ServerResponse,
    token: string,
  ): Promise<void> {
    if (
      request.socket.remoteAddress !== "127.0.0.1" ||
      request.method !== "POST" ||
      request.url !== "/v1/resolve" ||
      !authorized(request, token)
    ) {
      writeJson(response, 404, { value: null });
      return;
    }
    try {
      const payload = await body(request);
      if (
        !isRecord(payload) ||
        typeof payload.credential_ref !== "string" ||
        !CREDENTIAL_REF_PATTERN.test(payload.credential_ref)
      ) {
        writeJson(response, 400, { value: null });
        return;
      }
      writeJson(response, 200, { value: await this.secrets.resolve(payload.credential_ref) });
    } catch {
      writeJson(response, 400, { value: null });
    }
  }
}
