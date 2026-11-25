import { existsSync, mkdirSync, readdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join, posix, resolve, sep } from "node:path";
import ts from "typescript";

// Inspect emitted CommonJS, rather than source imports which may be tree-shaken.
export function inspectWeixinPackages(directory) {
  const app = JSON.parse(readFileSync(join(directory, "app.json"), "utf8"));
  const groups = app.subPackages || app.subpackages || [];
  const roots = groups.map(({ root }) => root.replace(/^\/+|\/+$/g, ""));
  const owner = (file) => roots.find((root) => file.startsWith(`${root}/`)) || "";
  const modules = new Map();
  const json = new Map();
  function walk(relative = "") {
    for (const entry of readdirSync(join(directory, relative), { withFileTypes: true })) {
      const file = posix.join(relative, entry.name);
      if (entry.isDirectory()) walk(file);
      else if (file.endsWith(".js")) {
        const code = readFileSync(join(directory, file), "utf8");
        const source = ts.createSourceFile(file, code, ts.ScriptTarget.Latest, true, ts.ScriptKind.JS);
        const references = [];
        function visit(node) {
          if (ts.isCallExpression(node) && ts.isIdentifier(node.expression) && node.expression.text === "require") {
            const argument = node.arguments[0];
            if (argument && ts.isStringLiteralLike(argument))
              references.push({ specifier: argument.text, start: argument.getStart(source), end: argument.end });
          }
          ts.forEachChild(node, visit);
        }
        visit(source);
        modules.set(file, { code, references });
      } else if (file.endsWith(".json") && !/^project\./.test(file)) {
        json.set(file, JSON.parse(readFileSync(join(directory, file), "utf8")));
      }
    }
  }
  walk();
  function target(from, specifier) {
    if (!specifier.startsWith(".") && !specifier.startsWith("/")) return;
    const path = specifier.startsWith("/")
      ? posix.normalize(specifier.slice(1))
      : posix.normalize(posix.join(posix.dirname(from), specifier));
    if (path === ".." || path.startsWith("../")) throw new Error(`微信代码包引用越界：${from} → ${specifier}`);
    return modules.has(path) ? path : `${path}.js`;
  }
  const missingReferences = [];
  const crossPackageReferences = [];
  const dependencies = new Map();
  for (const [file, module] of modules) {
    const refs = module.references.map((ref) => ({ ...ref, target: target(file, ref.specifier) }));
    module.references = refs;
    const components = Object.values(json.get(file.replace(/\.js$/, ".json"))?.usingComponents || {})
      .map((specifier) => target(file, specifier)).filter(Boolean);
    const targets = [...refs.map((ref) => ref.target).filter(Boolean), ...components];
    dependencies.set(file, targets);
    for (const to of targets) {
      if (!modules.has(to)) missingReferences.push(`${file} → ${to}`);
      if (owner(to) && owner(to) !== owner(file)) crossPackageReferences.push(`${file} → ${to}`);
    }
  }
  function reachable(seeds) {
    const found = new Set();
    const pending = [...seeds];
    while (pending.length) {
      const file = pending.pop();
      if (found.has(file) || !modules.has(file)) continue;
      found.add(file);
      pending.push(...(dependencies.get(file) || []));
    }
    return found;
  }
  const mainSeeds = ["app.js", ...(app.pages || []).map((page) => `${page}.js`)];
  // Main-package component entry scripts are loaded by the component runtime,
  // including components registered lazily by subpackage pages.
  for (const [file, config] of json) {
    if (!owner(file) && config.component === true)
      mainSeeds.push(file.replace(/\.json$/, ".js"));
  }
  for (const specifier of Object.values(app.usingComponents || {})) {
    const file = target("app.js", specifier);
    if (file) mainSeeds.push(file);
  }
  if (app.tabBar?.custom) mainSeeds.push("custom-tab-bar/index.js");
  if (app.workers) {
    const workers = typeof app.workers === "string" ? app.workers : app.workers.path;
    if (workers) mainSeeds.push(...[...modules.keys()].filter((file) => file.startsWith(`${workers}/`)));
  }
  const mainReachable = reachable(mainSeeds);
  const packageReachable = new Map(groups.map((group) => [
    group.root.replace(/^\/+|\/+$/g, ""),
    reachable(group.pages.map((page) => `${group.root}/${typeof page === "string" ? page : page.path}.js`)),
  ]));
  const unusedMainJs = [...modules.keys()].filter((file) => !owner(file) && !mainReachable.has(file));
  return { modules, owner, mainReachable, packageReachable, unusedMainJs, missingReferences, crossPackageReferences };
}

// Only emitted files inside the supplied output directory are changed. Shared
// main-package dependencies retain their original identity (auth, stores, etc.).
export function optimizeWeixinPackages(directory, { relocateSubpackageModules = true } = {}) {
  const output = resolve(directory);
  const graph = inspectWeixinPackages(output);
  if (graph.missingReferences.length || graph.crossPackageReferences.length)
    throw new Error(`微信分包依赖无效：${[...graph.missingReferences, ...graph.crossPackageReferences].join("；")}`);
  const plans = new Map();
  for (const file of graph.unusedMainJs) {
    const users = [...graph.packageReachable].filter(([, files]) => files.has(file)).map(([root]) => root);
    if (!relocateSubpackageModules && users.length) continue;
    // Components carry JSON/template/style sidecars and require a separate
    // relocation contract. Multi-package state modules must not be duplicated.
    if (existsSync(join(output, file.replace(/\.js$/, ".json")))) continue;
    if (users.length > 1 && !file.startsWith("api/")) continue;
    if (existsSync(join(output, `${file}.map`)))
      throw new Error(`微信分包 JS 优化暂不支持 source map：${file}`);
    plans.set(file, new Map(users.map((root) => [root, `${root}/_shared/${file}`])));
  }
  function rewrite(original, emitted, root) {
    let code = graph.modules.get(original).code;
    for (const ref of [...graph.modules.get(original).references].reverse()) {
      if (!ref.target) continue;
      const to = plans.get(ref.target)?.get(root) || ref.target;
      let specifier = posix.relative(posix.dirname(emitted), to);
      if (!specifier.startsWith(".")) specifier = `./${specifier}`;
      code = code.slice(0, ref.start) + JSON.stringify(specifier) + code.slice(ref.end);
    }
    return code;
  }
  const writes = new Map();
  for (const [file, copies] of plans) {
    for (const [root, emitted] of copies) writes.set(emitted, rewrite(file, emitted, root));
  }
  for (const [file] of graph.modules) {
    const root = graph.owner(file);
    if (root && relocateSubpackageModules) {
      const code = rewrite(file, file, root);
      if (code !== graph.modules.get(file).code) writes.set(file, code);
    }
  }
  const safePath = (file) => {
    const path = resolve(output, file);
    if (!path.startsWith(output + sep)) throw new Error("微信分包输出路径越界");
    return path;
  };
  // Validate destinations before writing or removing anything.
  for (const file of [...writes.keys(), ...plans.keys()]) safePath(file);
  for (const [file, code] of writes) {
    mkdirSync(dirname(safePath(file)), { recursive: true });
    writeFileSync(safePath(file), code);
  }
  for (const file of plans.keys()) rmSync(safePath(file));
  return { relocatedModules: plans.size, packageCopies: [...plans.values()].reduce((n, copies) => n + copies.size, 0) };
}

// Default builds only remove JS unreachable from every page/component. Keep
// subpackage files and require paths intact until relocation passes device QA.
export function weixinUnusedModuleCleanup() {
  return {
    name: "weixin-unused-module-cleanup",
    apply: "build",
    writeBundle: {
      order: "post",
      sequential: true,
      handler(options) {
        if (process.env.UNI_PLATFORM !== "mp-weixin" || !options.dir) return;
        const result = optimizeWeixinPackages(options.dir, { relocateSubpackageModules: false });
        console.log(`微信未引用 JS 清理：${result.relocatedModules} 个模块，不搬迁或复制分包依赖`);
      },
    },
  };
}
