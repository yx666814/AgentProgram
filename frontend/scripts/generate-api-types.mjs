import fs from "node:fs/promises";

import openapiTS, { astToString } from "openapi-typescript";

const schema = JSON.parse(await fs.readFile("contracts/openapi.json", "utf8"));
const output = astToString(await openapiTS(schema));

await fs.mkdir("src/api", { recursive: true });
await fs.writeFile(
  "src/api/generated.ts",
  `// Generated from contracts/openapi.json. Do not edit.\n${output}`,
  "utf8",
);
