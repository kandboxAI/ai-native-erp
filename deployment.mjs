import { readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { readPluginManifests } from "./plugin-manifests.mjs";

const defaultPath = fileURLToPath(new URL("./deployment.json", import.meta.url));
const repositoryRoot = fileURLToPath(new URL(".", import.meta.url));

// 仅组合构建校验使用临时文件覆盖；正常开发和发布读取仓库根目录 deployment.json。
export function readDeployment(path = process.env.FRONTEND_DEPLOYMENT_FILE || defaultPath, root = repositoryRoot) {
  let document;
  try {
    document = JSON.parse(readFileSync(path, "utf8"));
  } catch (error) {
    throw new Error(`无法读取部署清单 ${path}: ${error.message}`, { cause: error });
  }
  if (
    !document ||
    Array.isArray(document) ||
    typeof document !== "object" ||
    Object.keys(document).sort().join(",") !== "format_version,plugins" ||
    document.format_version !== 1
  ) {
    throw new Error("部署清单只能包含 format_version=1 和 plugins");
  }
  let plugins = document.plugins;
  if (
    !Array.isArray(plugins) ||
    plugins.some(key => typeof key !== "string") ||
    new Set(plugins).size !== plugins.length
  ) {
    throw new Error("部署清单 plugins 必须是无重复的字符串数组；空数组表示仅加载底座");
  }
  for (const entry of Object.values(readPluginManifests(root))) {
    const retired = plugins.filter(key => entry.replaces.includes(key));
    if (retired.length && !plugins.includes(entry.key)) throw new Error(`插件 ${retired.join(", ")} 已合并到 ${entry.key}，请明确选择 ${entry.key}`);
    plugins = plugins.filter(key => !retired.includes(key));
  }
  const manifests = new Map();
  const pluginRoot = join(root, "plugins");
  for (const key of plugins) {
    if (!/^[a-z][a-z0-9_]*$/.test(key)) throw new Error(`能力包标识无效：${key}`);
    const text = readFileSync(join(pluginRoot, key, "plugin.toml"), "utf8");
    const declarations = field => text.split(/\r?\n/).filter(line => new RegExp(`^[ \\t]*${field}[ \\t]*=`).test(line));
    const stringValue = field => {
      const rows = declarations(field);
      if (rows.length !== 1) return undefined;
      const value = rows[0].match(/^[ \t]*[a-z_]+[ \t]*=[ \t]*(?:"([^"\r\n]*)"|'([^'\r\n]*)')[ \t]*(?:#.*)?$/);
      return value?.[1] ?? value?.[2];
    };
    const name = stringValue("key");
    const version = stringValue("version");
    const layer = stringValue("layer");
    const listMatches = [...text.matchAll(/^[ \t]*requires[ \t]*=[ \t]*\[([\s\S]*?)\][ \t]*(?:#.*)?$/gm)];
    const list = listMatches.length === 1 ? listMatches[0][1] : undefined;
    if (name !== key || !version || !layer || list === undefined) throw new Error(`能力包清单无效：${key}`);
    if (!/^\d+(?:\.\d+){1,2}$/.test(version) || !["L1", "L2", "L3"].includes(layer)) throw new Error(`能力包版本或层级无效：${key}`);
    const clean = list.replace(/#[^\n]*/g, "");
    const values = [...clean.matchAll(/(?:"([a-z][a-z0-9_]*(?:>=\d+(?:\.\d+){1,2})?)"|'([a-z][a-z0-9_]*(?:>=\d+(?:\.\d+){1,2})?)')/g)];
    const requirements = values.map(match => match[1] ?? match[2]);
    if (new Set(requirements).size !== values.length) throw new Error(`requires 不能重复：${key}`);
    if (clean.replace(/(?:"[a-z][a-z0-9_]*(?:>=\d+(?:\.\d+){1,2})?"|'[a-z][a-z0-9_]*(?:>=\d+(?:\.\d+){1,2})?')/g, "").replace(/[\s,]/g, "")) throw new Error(`requires 格式无效：${key}`);
    const migrationBase = stringValue("migration_base") || "core";
    if (declarations("migration_base").length > 0 && !["core", "tenant"].includes(migrationBase)) throw new Error(`migration_base 无效：${key}`);
    if (migrationBase !== "core") throw new Error(`开源底座只接受 core 基线插件：${key}`);
    manifests.set(key, { version, layer, migrationBase, requires: requirements });
  }
  const visited = new Set(), active = new Set();
  function visit(key) {
    if (active.has(key)) throw new Error(`能力包依赖成环：${key}`);
    if (visited.has(key)) return;
    active.add(key);
    for (const spec of manifests.get(key).requires) {
      const [dependency, minimum] = spec.split(">=");
      if (!manifests.has(dependency)) throw new Error(`${key} 缺少依赖 ${dependency}`);
      if (minimum) {
        const current = manifests.get(dependency).version.split(".").map(Number), required = minimum.split(".").map(Number);
        for (let index = 0; index < Math.max(current.length, required.length); index++) {
          const difference = (current[index] || 0) - (required[index] || 0);
          if (difference < 0) throw new Error(`${key} 要求 ${spec}`);
          if (difference > 0) break;
        }
      }
      visit(dependency);
    }
    active.delete(key); visited.add(key);
  }
  for (const key of plugins) visit(key);
  for (const [key, manifest] of manifests) {
    if (manifest.layer === "L2" && manifest.requires.some(spec => manifests.get(spec.split(">=")[0]).layer === "L3")) throw new Error(`L2 插件 ${key} 不能依赖 L3 插件`);
  }
  const bases = new Set([...manifests.values()].map(manifest => manifest.migrationBase));
  if (bases.size > 1) throw new Error("不能混合 core 与历史 tenant 基线的插件");
  const profile = plugins.length ? "custom" : "core";
  return { profile, plugins, migrationBase: [...bases][0] || "core" };
}
