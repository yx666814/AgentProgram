import { rm } from "node:fs/promises";

import { build } from "esbuild";

await rm("dist/electron", { force: true, recursive: true });

await Promise.all([
  build({
    entryPoints: ["electron/main.ts"],
    outfile: "dist/electron/main.js",
    bundle: true,
    format: "esm",
    platform: "node",
    target: "node24",
    external: ["electron"],
    sourcemap: true,
    legalComments: "none",
  }),
  build({
    entryPoints: ["electron/preload.ts"],
    outfile: "dist/electron/preload.cjs",
    bundle: true,
    format: "cjs",
    platform: "node",
    target: "node24",
    external: ["electron"],
    sourcemap: true,
    legalComments: "none",
  }),
]);

