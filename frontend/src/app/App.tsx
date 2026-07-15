import { BrowserRouter } from "react-router-dom";

import type { DesktopPort } from "../../electron/desktop-port";
import { BackendProvider } from "../api/backend-context";
import { ThemeProvider } from "../theme/theme-provider";
import { AppRoutes } from "./routes";

export interface AppProps {
  desktopPort?: DesktopPort | null;
}

export function App({ desktopPort }: AppProps) {
  return (
    <ThemeProvider>
      <BackendProvider {...(desktopPort !== undefined ? { port: desktopPort } : {})}>
        <BrowserRouter>
          <AppRoutes />
        </BrowserRouter>
      </BackendProvider>
    </ThemeProvider>
  );
}
