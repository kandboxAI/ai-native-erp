import { readFileSync, realpathSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, resolve } from "node:path";

const require = createRequire(import.meta.url);
const manifestPath = realpathSync(require.resolve("markdown-it/package.json"));
const manifest = JSON.parse(readFileSync(manifestPath, "utf8"));
const entry = manifest.exports?.["."]?.import?.default;
if (typeof entry !== "string")
  throw new Error("无法解析 markdown-it 的标准 ESM 入口，请检查依赖版本");

// The browser and CJS bundles embed entity tables that require global atob.
// Resolve the standard ESM entry from the real pnpm package directory so
// uni-app can also resolve its dependencies with preserveSymlinks enabled.
export const markdownItEntry = resolve(dirname(manifestPath), entry);
