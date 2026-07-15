import { ApiRequestError } from "../api/errors";
import { Button } from "./button";

function errorDetails(error: unknown): { code: string; message: string; retryable: boolean } {
  if (error instanceof ApiRequestError) {
    return { code: error.code, message: error.message, retryable: error.retryable };
  }
  if (error instanceof Error) {
    return { code: "client.unexpected_error", message: error.message, retryable: false };
  }
  return { code: "client.unknown_error", message: "发生未知错误", retryable: false };
}

export function ApiErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const details = errorDetails(error);
  return (
    <div className="api-error-state" role="alert">
      <strong>{details.message}</strong>
      <code>{details.code}</code>
      {details.retryable && onRetry !== undefined ? <Button onClick={onRetry}>重试</Button> : null}
    </div>
  );
}
