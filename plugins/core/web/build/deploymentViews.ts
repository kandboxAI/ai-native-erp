import type { Plugin } from "vite";
import {
  coreFrontend,
  readPluginFrontends,
  repositoryRoot
} from "../../../../plugin-frontends.mjs";
import { normalizePath } from "vite";
import {
  pluginSourcePath,
  pluginWebSourceRoots
} from "../../../../plugin-sources.mjs";
import { readdirSync } from "node:fs";
import { join, relative } from "node:path";

const moduleId = "virtual:deployed-views";
const resolvedId = `\0${moduleId}`;

type SidebarGroup = { icon?: string; children: (string | SidebarGroup)[] };

function sidebarIconImports(
  items: (string | SidebarGroup)[],
  icons: Set<string>
) {
  for (const item of items) {
    if (typeof item === "string") continue;
    if (item.icon) icons.add(item.icon);
    sidebarIconImports(item.children, icons);
  }
}

export function deploymentViews(plugins: string[]): Plugin {
  let pluginFrontends = readPluginFrontends();
  const manifestFiles = new Set(
    plugins.map(key =>
      normalizePath(join(repositoryRoot, "plugins", key, "frontend.json"))
    )
  );
  const patterns = coreFrontend.web_view_roots.map(
    root => `/src/views/${root}/**/*.{vue,tsx}`
  );
  function pageImports() {
    const entries: string[] = [];
    for (const key of plugins)
      for (const view of pluginFrontends[key]?.web_view_roots || []) {
        const directory = pluginSourcePath(key, `web/src/views/${view}`);
        const visit = (folder: string) => {
          for (const entry of readdirSync(folder, { withFileTypes: true })) {
            const path = join(folder, entry.name);
            if (entry.isSymbolicLink())
              throw new Error(`插件页面不能使用链接：${path}`);
            if (entry.isDirectory()) visit(path);
            else if (/\.(vue|tsx)$/.test(entry.name)) {
              const logical = `/src/views/${view}/${relative(directory, path).replaceAll("\\", "/")}`;
              entries.push(
                `${JSON.stringify(logical)}: () => import(${JSON.stringify("/@fs/" + path.replaceAll("\\", "/"))})`
              );
            }
          }
        };
        visit(directory);
      }
    return entries.join(",\n");
  }
  return {
    name: "deployment-views",
    configureServer(server) {
      if (server.config?.server.watch === null) return;
      // 监听整个已部署插件源码，新增依赖也能清除失败的解析缓存。
      server.watcher.add(pluginWebSourceRoots(plugins));
      server.watcher.add([...manifestFiles]);
      server.watcher.on("all", (event, file) => {
        const path = normalizePath(file);
        const directories = plugins.flatMap(key =>
          (pluginFrontends[key]?.web_view_roots || []).map(view =>
            normalizePath(pluginSourcePath(key, `web/src/views/${view}`))
          )
        );
        if (
          !["add", "unlink"].includes(event) ||
          !/\.(vue|tsx)$/.test(path) ||
          !directories.some(directory => path.startsWith(`${directory}/`))
        )
          return;
        const module = server.moduleGraph.getModuleById(resolvedId);
        if (module) server.moduleGraph.invalidateModule(module);
        server.ws.send({ type: "full-reload" });
      });
    },
    async handleHotUpdate(context) {
      if (!manifestFiles.has(normalizePath(context.file))) return;
      await context.read();
      pluginFrontends = readPluginFrontends();
      for (const id of [
        resolvedId,
        "workbench-calendar",
        "sidebar-layouts",
        "workflow-routes",
        "platform-workbench",
        "business-route-roots",
        "plugin-applications"
      ].map(id => (id.startsWith("\0") ? id : `\0virtual:${id}`))) {
        const module = context.server.moduleGraph.getModuleById(id);
        if (module) context.server.moduleGraph.invalidateModule(module);
      }
      context.server.ws.send({ type: "full-reload" });
      return [];
    },
    resolveId(id) {
      if (id === "virtual:workbench-calendar")
        return "\0virtual:workbench-calendar";
      if (id === "virtual:sidebar-layouts") return "\0virtual:sidebar-layouts";
      if (id === "virtual:workflow-routes") return "\0virtual:workflow-routes";
      if (id === "virtual:platform-workbench")
        return "\0virtual:platform-workbench";
      if (id === "virtual:business-route-roots")
        return "\0virtual:business-route-roots";
      if (id === "virtual:plugin-applications")
        return "\0virtual:plugin-applications";
      if (id === moduleId) return resolvedId;
    },
    load(id) {
      if (id === "\0virtual:workbench-calendar") {
        const entry = plugins
          .map(key => ({
            key,
            path: pluginFrontends[key]?.web_calendar_provider
          }))
          .find(item => item.path);
        return entry
          ? `export default () => import(${JSON.stringify("/@fs/" + pluginSourcePath(entry.key, `web/src/${entry.path}`).replaceAll("\\", "/"))});`
          : "export default null;";
      }
      if (id === "\0virtual:sidebar-layouts") {
        const layouts = plugins.flatMap(key => {
          const layout = pluginFrontends[key]?.web_sidebar;
          return layout ? [layout] : [];
        });
        const icons = new Set<string>();
        for (const layout of layouts) sidebarIconImports(layout.items, icons);
        const imports = [...icons].map(
          (icon, index) =>
            `import icon${index} from ${JSON.stringify(`~icons/${icon.replace(":", "/")}?raw`)};`
        );
        const entries = [...icons].map(
          (icon, index) => `${JSON.stringify(icon)}: icon${index}`
        );
        return `${imports.join("\n")}\nexport const sidebarIcons = {${entries.join(",")}};\nexport default ${JSON.stringify(layouts)};`;
      }
      if (id === "\0virtual:workflow-routes")
        return `export default ${JSON.stringify(Object.assign({}, ...plugins.map(key => pluginFrontends[key]?.workflow_routes || {})))};`;
      if (id === "\0virtual:platform-workbench") {
        const entries = plugins.flatMap(key =>
          pluginFrontends[key]?.web_workbench
            ? [
                pluginSourcePath(
                  key,
                  `web/src/views/${pluginFrontends[key].web_workbench}.vue`
                ).replaceAll("\\", "/")
              ]
            : []
        );
        const component =
          entries.length === 1 ? entries[0] : "/src/views/workbench/index.vue";
        return `export default () => import(${JSON.stringify(component.startsWith("/src/") ? component : "/@fs/" + component)});`;
      }
      if (id === "\0virtual:business-route-roots")
        return `export default ${JSON.stringify(["/system", "/monitor", "/permission", ...Object.keys(pluginFrontends).flatMap(key => pluginFrontends[key].web_view_roots.map(root => "/" + root))])};`;
      if (id === "\0virtual:plugin-applications")
        return `export default ${JSON.stringify(plugins.flatMap(key => pluginFrontends[key]?.web_applications || []))};`;
      if (id === resolvedId)
        return `export default { ...import.meta.glob(${JSON.stringify(patterns)}), ${pageImports()} };`;
    }
  };
}
