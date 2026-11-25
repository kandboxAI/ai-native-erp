/** plugin.toml 固定声明 frontend.json；业务页面与入口由各包维护。 */
import { readFileSync, existsSync } from "node:fs";
import { join } from "node:path";
import { readPluginManifests, repositoryRoot } from "./plugin-manifests.mjs";
import { validateBranding } from "./branding-schema.mjs";

export { repositoryRoot };
export const coreFrontend = JSON.parse(readFileSync(join(repositoryRoot, "plugins/core/backend/app/framework/core_manifest.json"), "utf8"));

export function readPluginFrontends(root = repositoryRoot) {
  const result = {};
  if (!existsSync(join(root, "plugins"))) return Object.freeze(result);
  for (const entry of Object.values(readPluginManifests(root))) {
    if (entry.frontend_manifest === undefined) continue;
    if (entry.frontend_manifest !== "frontend.json")
      throw new Error(
        `${entry.key}: plugin.toml 必须声明 frontend_manifest = "frontend.json"`,
      );
    const source = JSON.parse(
      readFileSync(join(root, "plugins", entry.key, "frontend.json"), "utf8"),
    );
    if (
      source.format_version !== 1 ||
      Object.keys(source).filter(key => !["web_applications", "web_workbench", "web_calendar_provider", "workflow_routes", "branding", "web_sidebar"].includes(key)).sort().join(",") !==
        "format_version,miniapp_pages,miniapp_service_provider,web_view_roots"
    )
      throw new Error(`${entry.key}: 前端清单格式无效`);
    if (source.branding !== undefined)
      validateBranding(source.branding, entry.key, { requireTitle: true });
    if (source.web_calendar_provider !== undefined && (
      typeof source.web_calendar_provider !== "string" || !/^[a-zA-Z][a-zA-Z0-9/-]*\.ts$/.test(source.web_calendar_provider) ||
      !existsSync(join(root, "plugins", entry.key, "web/src", source.web_calendar_provider))
    )) throw new Error(`${entry.key}: 工作台日程提供器无效`);
    if (source.web_sidebar !== undefined) {
      const menuKey = value => typeof value === "string" && /^[A-Za-z][A-Za-z0-9_]*$/.test(value);
      const used = new Set();
      const useKey = key => {
        if (!menuKey(key) || used.has(key)) return false;
        used.add(key);
        return true;
      };
      const validItem = item => typeof item === "string" ? useKey(item) :
        item && typeof item.title === "string" && item.title.trim() &&
        (item.menu === undefined || useKey(item.menu)) &&
        (item.icon === undefined || (typeof item.icon === "string" && /^ri:[a-z0-9-]+$/.test(item.icon))) &&
        (item.showParent === undefined || typeof item.showParent === "boolean") &&
        (item.trailing === undefined || (Array.isArray(item.trailing) && item.trailing.every(useKey))) &&
        Array.isArray(item.children) && item.children.length && item.children.every(validItem);
      const sidebar = source.web_sidebar;
      if (!sidebar || !Array.isArray(sidebar.anchors) || !sidebar.anchors.length ||
          !sidebar.anchors.every(menuKey) || !Array.isArray(sidebar.items) ||
          !sidebar.items.length || !sidebar.items.every(validItem))
        throw new Error(`${entry.key}: web_sidebar 无效或包含重复菜单`);
    }
    if (source.web_workbench !== undefined && (typeof source.web_workbench !== "string" || !/^[a-z][a-z0-9-]*\/[a-z][a-z0-9/-]*$/.test(source.web_workbench) || !source.web_view_roots.includes(source.web_workbench.split("/")[0]))) throw new Error(`${entry.key}: 工作台归属无效`);
    if (source.workflow_routes !== undefined && (!source.workflow_routes || Array.isArray(source.workflow_routes) || typeof source.workflow_routes !== "object" || Object.entries(source.workflow_routes).some(([key, value]) => !/^[a-z][a-z0-9_]*$/.test(key) || typeof value !== "string" || !/^[A-Za-z][A-Za-z0-9_]*$/.test(value)))) throw new Error(`${entry.key}: workflow_routes 无效`);
    const applications = source.web_applications || [];
    if (!Array.isArray(applications) || applications.some(item => !item || Object.keys(item).sort().join(",") !== "icon,path,rootPath,summary,title,tone" || Object.values(item).some(value => typeof value !== "string" || !value) || !["blue","cyan","violet","green","orange","rose"].includes(item.tone) || !/^\/[a-z][a-z0-9/-]*$/.test(item.path) || !/^\/[a-z][a-z0-9/-]*$/.test(item.rootPath))) throw new Error(`${entry.key}: 应用入口定义无效`);
    for (const [field, pattern] of [
      ["miniapp_pages", /^pages\/[a-z][a-z0-9-]*\/[a-z][a-z0-9-]*$/],
      ["web_view_roots", /^[a-z][a-z0-9-]*$/],
    ]) {
      if (
        !Array.isArray(source[field]) ||
        source[field].some(
          (value) => typeof value !== "string" || !pattern.test(value),
        ) ||
        new Set(source[field]).size !== source[field].length
      )
        throw new Error(`${entry.key}: ${field} 定义无效`);
    }
    if (
      typeof source.miniapp_service_provider !== "string" ||
      !/^miniprogram\/[a-z][a-z0-9_-]*\.ts$/.test(
        source.miniapp_service_provider,
      ) ||
      !existsSync(
        join(root, "plugins", entry.key, source.miniapp_service_provider),
      )
    )
      throw new Error(`${entry.key}: 小程序提供器无效`);
    result[entry.key] = Object.freeze(source);
  }
  const workflowOwners = new Map();
  for (const [key, manifest] of Object.entries(result)) {
    for (const type of Object.keys(manifest.workflow_routes || {})) {
      if (workflowOwners.has(type)) throw new Error(`审批跳转归属重复：${type}`);
      workflowOwners.set(type, key);
    }
  }
  return Object.freeze(result);
}

export const pluginFrontends = readPluginFrontends();
export const coreMiniappPages = JSON.parse(
  readFileSync(
    join(repositoryRoot, "plugins/core/backend/app/framework/miniapp_core.json"),
    "utf8",
  ),
).pages;
