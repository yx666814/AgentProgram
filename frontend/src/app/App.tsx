import { BrowserRouter, HashRouter } from "react-router-dom";

import type { DesktopPort } from "../../electron/desktop-port";
import { BackendProvider } from "../api/backend-context";
import { ThemeProvider } from "../theme/theme-provider";
import { AppRoutes } from "./routes";

export interface AppProps {
  desktopPort?: DesktopPort | null;
}

export function App({ desktopPort }: AppProps) {
  const Router = window.location.protocol === "file:" ? HashRouter : BrowserRouter;
  return (
    <ThemeProvider>
      <BackendProvider {...(desktopPort !== undefined ? { port: desktopPort } : {})}>
        <Router>
          <AppRoutes />
        </Router>
      </BackendProvider>
    </ThemeProvider>
  );
}
