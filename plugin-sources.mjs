/** Physical source locations for contained and legacy source plugins. */
import { join, resolve, relative, isAbsolute } from "node:path";
import { existsSync, realpathSync } from "node:fs";
import { readPluginManifests, repositoryRoot } from "./plugin-manifests.mjs";

export function pluginSourcePath(key, logical, root = repositoryRoot) {
  const manifest = readPluginManifests(root)[key];
  if (!manifest) throw new Error(`插件不存在：${key}`);
  if (
    isAbsolute(logical) ||
    logical.includes("\\") ||
    logical.split("/").includes("..")
  )
    throw new Error(`插件路径无效：${logical}`);
  const contained =
    manifest.source_layout === "contained" &&
    /^(backend\/app|web\/src|miniprogram\/src)(\/|$)/.test(logical);
  const path = resolve(root, contained ? `plugins/${key}` : "", logical);
  const checked = existsSync(path) ? realpathSync(path) : path;
  const rel = relative(realpathSync(root), checked);
  if (
    rel === ".." ||
    rel.startsWith("../") ||
    rel.startsWith("..\\") ||
    isAbsolute(rel)
  )
    throw new Error(`插件路径越界：${logical}`);
  return path;
}

/** Assets follow imports from the plugin's web/src tree, including its own assets. */
export function pluginWebSourceRoots(keys, root = repositoryRoot) {
  const manifests = readPluginManifests(root);
  return keys
    .filter((key) => manifests[key]?.source_layout === "contained")
    .map((key) => join(root, "plugins", key, "web/src"));
}
