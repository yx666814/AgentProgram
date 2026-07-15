import type { DesktopPort } from "../../electron/desktop-port";

export interface NativeConfirmRequest {
  title: string;
  message: string;
  detail: string;
  confirmLabel: string;
}

export async function requireNativeConfirm(
  port: DesktopPort | null,
  request: NativeConfirmRequest,
): Promise<boolean> {
  if (port === null) {
    return false;
  }
  return port.showNativeConfirm(request);
}
