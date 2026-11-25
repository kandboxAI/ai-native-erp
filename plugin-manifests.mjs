/** 构建时读取插件的固定字符串声明；完整清单和依赖校验仍由后端加载器负责。 */
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

export const repositoryRoot = fileURLToPath(new URL(".", import.meta.url));

function replacedKeys(toml, path) {
  const declarations = [...toml.matchAll(/^[ \t]*replaces[ \t]*=/gm)];
  if (!declarations.length) return [];
  const rows = [
    ...toml.matchAll(
      /^[ \t]*replaces[ \t]*=[ \t]*\[([\s\S]*?)\][ \t]*(?:#[^\r\n]*)?\r?$/gm,
    ),
  ];
  if (declarations.length !== 1 || rows.length !== 1)
    throw new Error(`${path}: replaces 无效`);
  const clean = rows[0][1].replace(/#[^\n]*/g, "");
  const values = [
    ...clean.matchAll(/(?:"([a-z][a-z0-9_]*)"|'([a-z][a-z0-9_]*)')/g),
  ].map((row) => row[1] ?? row[2]);
  if (
    new Set(values).size !== values.length ||
    values.includes("core") ||
    clean
      .replace(/(?:"[a-z][a-z0-9_]*"|'[a-z][a-z0-9_]*')/g, "")
      .replace(/[\s,]/g, "")
  )
    throw new Error(`${path}: replaces 无效`);
  return values;
}

function literal(toml, field, path, required = true) {
  const declarations = [
    ...toml.matchAll(new RegExp(`^[ \\t]*${field}[ \\t]*=`, "gm")),
  ];
  if (!required && declarations.length === 0) return undefined;
  // 只接受单行字面量，不执行清单内容；兼容 TOML 的单双引号和行尾注释。
  const values = [
    ...toml.matchAll(
      new RegExp(
        `^[ \\t]*${field}[ \\t]*=[ \\t]*(?:"([^"\\\\\\r\\n]*)"|'([^'\\r\\n]*)')[ \\t]*(?:#[^\\r\\n]*)?\\r?$`,
        "gm",
      ),
    ),
  ];
  if (declarations.length !== 1 || values.length !== 1)
    throw new Error(`${path}: ${field} 必须声明一次且为单行字符串字面量`);
  return values[0][1] ?? values[0][2];
}

export function readPluginManifests(root = repositoryRoot) {
  const result = {};
  const directory = join(root, "plugins");
  for (const entry of readdirSync(directory, { withFileTypes: true }).sort(
    (a, b) => a.name.localeCompare(b.name),
  )) {
    if (!entry.isDirectory()) continue;
    const path = join(directory, entry.name, "plugin.toml");
    if (!existsSync(path)) continue;
    const toml = readFileSync(path, "utf8");
    const key = literal(toml, "key", path);
    const layer = literal(toml, "layer", path);
    if (key !== entry.name || !/^[a-z][a-z0-9_]*$/.test(key))
      throw new Error(`${path}: key 必须与插件目录名一致且使用小写 snake_case`);
    if (!["L1", "L2", "L3"].includes(layer))
      throw new Error(`${path}: layer 必须为 L1、L2 或 L3`);
    const replaces = replacedKeys(toml, path);
    if (replaces.includes(key))
      throw new Error(`${path}: replaces 不能接管自身`);
    const source_layout =
      literal(toml, "source_layout", path, false) || "legacy";
    if (!["legacy", "contained"].includes(source_layout))
      throw new Error(`${path}: source_layout 必须为 legacy 或 contained`);
    result[key] = Object.freeze({
      key,
      layer,
      replaces,
      source_layout,
      frontend_manifest: literal(toml, "frontend_manifest", path, false),
    });
  }
  const owners = new Map();
  for (const entry of Object.values(result))
    for (const key of entry.replaces) {
      if (owners.has(key) && owners.get(key) !== entry.key)
        throw new Error(`插件 ${key} 被多个插件接管`);
      owners.set(key, entry.key);
    }
  for (const key of owners.keys()) {
    if (result[key]?.replaces.length)
      throw new Error("不支持插件接管链或接管环");
    delete result[key];
  }
  return Object.freeze(result);
}
