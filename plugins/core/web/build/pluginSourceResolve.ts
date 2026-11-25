import { join } from "node:path";
import { normalizePath, type Plugin } from "vite";

const fallback = "plugin-source-resolve-fallback";

/**
 * 插件源码在 web/ 之外。按导入文件向上查找 node_modules 到不了管理端依赖。
 * 裸导入改从管理端 package.json 所在目录解析，别名仍由 Vite 自己处理。
 */
export function resolvePluginSourceDependencies(
  appRoot: string,
  pluginRoots: string[]
): Plugin {
  const roots = pluginRoots.map(
    item => `${normalizePath(item).replace(/\/$/, "")}/`
  );
  const fromApp = join(appRoot, "package.json");
  return {
    name: "resolve-plugin-source-dependencies",
    enforce: "pre",
    async resolveId(id, importer, options) {
      if (!importer || options?.custom?.[fallback]) return null;
      if (
        id.startsWith(".") ||
        id.startsWith("/") ||
        id.startsWith("\0") ||
        id.startsWith("virtual:")
      )
        return null;
      const file = normalizePath(importer.split("?", 1)[0]);
      if (!roots.some(item => file.startsWith(item))) return null;
      return this.resolve(id, fromApp, {
        skipSelf: true,
        custom: { ...options?.custom, [fallback]: true }
      });
    }
  };
}
