/** 页面归属只来源于插件前端声明；部署选择仍读取 deployment.json。 */
import { pluginFrontends, coreMiniappPages } from "./plugin-frontends.mjs";
export { pluginFrontends };

export const webViewRoots = Object.freeze(
  Object.fromEntries(
    Object.entries(pluginFrontends).map(([key, manifest]) => [
      key,
      manifest.web_view_roots,
    ]),
  ),
);

const miniappOwners = new Map(coreMiniappPages.map((path) => [path, "core"]));
const rootOwners = new Map(
  coreMiniappPages.map((path) => [path.split("/")[1], "core"]),
);
for (const [key, definition] of Object.entries(pluginFrontends)) {
  for (const path of definition.miniapp_pages) {
    const root = path.split("/")[1];
    if (
      miniappOwners.has(path) ||
      (rootOwners.has(root) && rootOwners.get(root) !== key)
    )
      throw new Error(`小程序页面归属重复：${path}`);
    miniappOwners.set(path, key);
    rootOwners.set(root, key);
  }
}
export function miniappPageOwner(path) {
  const owner = miniappOwners.get(path);
  if (!owner) throw new Error(`小程序页面未声明能力包归属：${path}`);
  return owner;
}
export function miniappPageRootOwner(root) {
  const owner = rootOwners.get(root);
  if (!owner) throw new Error(`小程序页面目录未声明归属：${root}`);
  return owner;
}
/** 将主包与分包统一投影为完整路由；授权、归属和构建过滤共用此清单。 */
export function miniappPages(document) {
  const subPackages = document.subPackages || document.subpackages || [];
  return [...document.pages, ...subPackages.flatMap(group =>
    group.pages.map(page => ({ ...page, path: `${group.root}/${page.path}` })))];
}
export function selectMiniappPages(document, plugins) {
  const selected = new Set(plugins);
  const declaredPages = miniappPages(document);
  const declared = new Set(declaredPages.map((page) => page.path));
  if (declared.size !== declaredPages.length) throw new Error("小程序主包与分包路由重复");
  for (const path of miniappOwners.keys())
    if (!declared.has(path))
      throw new Error(`插件页面未注册到 pages.json：${path}`);
  const allowed = path => {
    const owner = miniappPageOwner(path);
    return owner === "core" || selected.has(owner);
  };
  const pages = document.pages.filter(page => allowed(page.path));
  const subPackages = (document.subPackages || document.subpackages || []).map(group => ({
    ...group, pages: group.pages.filter(page => allowed(`${group.root}/${page.path}`))
  })).filter(group => group.pages.length);
  const paths = new Set(pages.map((page) => page.path));
  const tabBar = document.tabBar && {
    ...document.tabBar,
    list: document.tabBar.list.filter((item) => paths.has(item.pagePath)),
  };
  if (document.tabBar?.list?.length && !tabBar.list.length)
    throw new Error("当前部署组合没有可用的小程序 tabBar 页面");
  const { subPackages: _subPackages, subpackages: _subpackages, ...main } = document;
  return { ...main, pages, ...(subPackages.length ? { subPackages } : {}), ...(tabBar ? { tabBar } : {}) };
}
export function excludedWebViewRoots(plugins) {
  const selected = new Set(plugins);
  return Object.entries(webViewRoots)
    .filter(([key]) => !selected.has(key))
    .flatMap(([, roots]) => roots);
}
