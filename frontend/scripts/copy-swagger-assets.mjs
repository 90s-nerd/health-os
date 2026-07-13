import { copyFileSync, mkdirSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const source = dirname(require.resolve("swagger-ui-dist/package.json"));
const frontend = join(dirname(fileURLToPath(import.meta.url)), "..");
const destination = join(frontend, "public", "docs-assets");

mkdirSync(destination, { recursive: true });

for (const filename of [
  "swagger-ui-bundle.js",
  "swagger-ui.css",
  "favicon-32x32.png",
]) {
  copyFileSync(join(source, filename), join(destination, filename));
}
