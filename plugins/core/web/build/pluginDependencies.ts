import { readFileSync } from "node:fs";
import { isAbsolute, relative, resolve } from "node:path";
import type { Plugin } from "vite";

function inside(root: string, file: string) {
  const path = relative(root, file);
  return (
    path !== ".." &&
    !path.startsWith("../") &&
    !path.startsWith("..\\") &&
    !isAbsolute(path)
  );
}

/** web 外的插件源码共用宿主声明的 npm 依赖，保留依赖内部的正常解析。 */
export function pluginDependencies(sourceRoots: string[]): Plugin {
  let hostImporter = "";
  let packages = new Set<string>();
  return {
    name: "plugin-host-dependencies",
    enforce: "pre",
    configResolved(config) {
      hostImporter = resolve(config.root, "package.json");
      const manifest = JSON.parse(readFileSync(hostImporter, "utf8"));
      packages = new Set([
        ...Object.keys(manifest.dependencies || {}),
        ...Object.keys(manifest.devDependencies || {})
      ]);
    },
    async resolveId(source, importer, options) {
      if (!importer || importer.startsWith("\0")) return;
      const file = importer.split("?", 1)[0];
      if (
        file.replaceAll("\\", "/").includes("/node_modules/") ||
        !sourceRoots.some(root => inside(root, file))
      )
        return;
      const packageName = source.match(/^(?:@[^/]+\/)?[^/?#]+/)?.[0];
      if (!packageName || !packages.has(packageName)) return;
      // Vite 继续处理 exports、browser 条件、子路径和 worker，不拼包内路径。
      return this.resolve(source, hostImporter, { ...options, skipSelf: true });
    }
  };
}
