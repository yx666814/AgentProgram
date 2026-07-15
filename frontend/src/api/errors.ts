export interface PublicApiError {
  code: string;
  message: string;
  retryable: boolean;
  statusCode: number;
  correlationId?: string;
  currentVersion?: string;
  details: Record<string, unknown>;
}

interface ErrorEnvelope {
  error: {
    code: string;
    message: string;
    retryable: boolean;
    details: Record<string, unknown>;
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isErrorEnvelope(value: unknown): value is ErrorEnvelope {
  if (!isRecord(value) || !isRecord(value.error)) {
    return false;
  }
  const { code, details, message, retryable } = value.error;
  return (
    typeof code === "string" &&
    typeof message === "string" &&
    typeof retryable === "boolean" &&
    isRecord(details)
  );
}

function readCurrentVersion(details: Record<string, unknown>): string | undefined {
  const version = details.current_version ?? details.actual_version ?? details.currentVersion;
  return typeof version === "string" || typeof version === "number" ? String(version) : undefined;
}

export class ApiRequestError extends Error implements PublicApiError {
  readonly code: string;
  readonly retryable: boolean;
  readonly statusCode: number;
  readonly details: Record<string, unknown>;
  readonly correlationId?: string;
  readonly currentVersion?: string;

  constructor(input: PublicApiError) {
    super(input.message);
    this.name = "ApiRequestError";
    this.code = input.code;
    this.retryable = input.retryable;
    this.statusCode = input.statusCode;
    this.details = input.details;
    if (input.correlationId !== undefined) {
      this.correlationId = input.correlationId;
    }
    if (input.currentVersion !== undefined) {
      this.currentVersion = input.currentVersion;
    }
  }
}

export function parseApiError(
  statusCode: number,
  payload: unknown,
  correlationId?: string,
): ApiRequestError {
  const envelope = isErrorEnvelope(payload)
    ? payload.error
    : {
        code: "client.invalid_error_envelope",
        message: "Backend returned an invalid error envelope",
        retryable: false,
        details: {},
      };
  const input: PublicApiError = {
    code: envelope.code,
    message: envelope.message,
    retryable: envelope.retryable,
    statusCode,
    details: envelope.details,
  };
  if (correlationId !== undefined) {
    input.correlationId = correlationId;
  }
  const currentVersion = readCurrentVersion(envelope.details);
  if (currentVersion !== undefined) {
    input.currentVersion = currentVersion;
  }
  return new ApiRequestError(input);
}
