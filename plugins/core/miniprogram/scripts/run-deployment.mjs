import {
  cpSync,
  existsSync,
  mkdirSync,
  readFileSync,
  rmSync,
  statSync,
  watch,
  writeFileSync,
} from "node:fs";
import { spawn } from "node:child_process";
import { dirname, join, relative, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";
import { readDeployment } from "../../../../deployment.mjs";
import { getProductBranding } from "../../../../product-branding.mjs";
import { resolveWeixinAppId } from "./weixin-release.mjs";
import { pluginSourcePath } from "../../../../plugin-sources.mjs";
import { readPluginManifests } from "../../../../plugin-manifests.mjs";
import {
  miniappPageRootOwner,
  miniappPages,
  selectMiniappPages,
  pluginFrontends,
} from "../../../../frontend-deployment.mjs";

const projectRoot = resolve(fileURLToPath(new URL("..", import.meta.url)));
const sourceRoot = join(projectRoot, "src");
const coreRoot = join(projectRoot, "core");
const generatedRoot = join(projectRoot, ".deployment-input");
const { profile, plugins } = readDeployment();
const useCoreShell = true;
const branding = getProductBranding(plugins);
const args = process.argv.slice(2);
const prepareOnly = args.includes("--prepare-only");
const isBuild = args[0] === "build";
const weixin = args.includes("mp-weixin") || args.includes("--platform=mp-weixin");
let weixinAppId;
if (weixin && !prepareOnly) {
  const { loadEnv } = await import("vite");
  const modeOption = args.indexOf("--mode");
  const mode = (modeOption >= 0 ? args[modeOption + 1] :
    args.find((arg) => arg.startsWith("--mode="))?.slice("--mode=".length)) ||
    (isBuild ? "production" : "development");
  const env = loadEnv(mode, projectRoot, "WEIXIN_");
  weixinAppId = resolveWeixinAppId(env.WEIXIN_APPID, { release: isBuild });
}
// 开发和构建独占输入目录，避免其他命令重建目录时打断 uni-app 热更新。
const generatedInput = resolve(
  generatedRoot,
  prepareOnly ? profile : `${profile}-${process.pid}`,
);
if (!generatedInput.startsWith(generatedRoot + sep)) {
  throw new Error("小程序构建输入目录越界");
}

const sourcePages = JSON.parse(
  readFileSync(join(sourceRoot, "pages.json"), "utf8"),
);
const selectedPages = selectMiniappPages(sourcePages, plugins);
selectedPages.globalStyle = {
  ...selectedPages.globalStyle,
  navigationBarTitleText: branding.title,
};
for (const page of selectedPages.pages) {
  if (
    ["pages/login/index", "pages/home/index", "pages/profile/index"].includes(
      page.path,
    )
  ) {
    page.style = { ...page.style, navigationBarTitleText: branding.title };
  }
}
const selectedPaths = new Set(miniappPages(selectedPages).map((page) => page.path));
const declaredRoots = new Set(
  miniappPages(sourcePages).map((page) => page.path.split("/")[1]),
);

function writeBrandedManifest() {
  const manifest = JSON.parse(
    readFileSync(join(sourceRoot, "manifest.json"), "utf8"),
  );
  manifest.name = branding.title;
  manifest.description = branding.description;
  manifest.h5 = { ...manifest.h5, title: branding.title };
  if (weixinAppId) manifest["mp-weixin"].appid = weixinAppId;
  writeFileSync(
    join(generatedInput, "manifest.json"),
    JSON.stringify(manifest, null, 2) + "\n",
  );
}

function copySourceFile(path, sourceBase = sourceRoot) {
  if (useCoreShell && existsSync(join(coreRoot, path))) return;
  const source = resolve(sourceBase, path);
  const target = resolve(generatedInput, path);
  if (
    !source.startsWith(sourceBase + sep) ||
    !target.startsWith(generatedInput + sep)
  ) {
    throw new Error("小程序文件同步路径越界");
  }
  if (path === "pages.json") {
    writeFileSync(target, JSON.stringify(selectedPages, null, 2) + "\n");
    return;
  }
  if (path === "manifest.json") {
    writeBrandedManifest();
    return;
  }
  if (path.startsWith(`pages${sep}`)) {
    const root = path.split(sep)[1];
    if (!declaredRoots.has(root)) return;
    const owner = miniappPageRootOwner(root);
    if (owner !== "core" && !plugins.includes(owner)) return;
  }
  if (!existsSync(source)) {
    if (existsSync(target)) rmSync(target, { recursive: true, force: true });
    return;
  }
  if (statSync(source).isDirectory()) {
    mkdirSync(target, { recursive: true });
    return;
  }
  mkdirSync(dirname(target), { recursive: true });
  cpSync(source, target);
}

rmSync(generatedInput, {
  recursive: true,
  force: true,
  maxRetries: 5,
  retryDelay: 100,
});
mkdirSync(generatedInput, { recursive: true });
cpSync(sourceRoot, generatedInput, {
  recursive: true,
  filter(path) {
    const item = relative(sourceRoot, path).replaceAll(sep, "/");
    if (!item || !item.startsWith("pages/")) return true;
    const root = item.split("/")[1];
    if (!declaredRoots.has(root)) return false;
    const owner = miniappPageRootOwner(root);
    return owner === "core" || plugins.includes(owner);
  },
});
writeFileSync(
  join(generatedInput, "pages.json"),
  JSON.stringify(selectedPages, null, 2) + "\n",
);
const pluginWatchers = [];
if (useCoreShell) {
  cpSync(coreRoot, generatedInput, { recursive: true });
  if (process.argv[2] !== "build")
    pluginWatchers.push(
      watch(coreRoot, { recursive: true }, () =>
        cpSync(coreRoot, generatedInput, { recursive: true }),
      ),
    );
}
writeBrandedManifest();
const providerImports = [];
const providerDefinitions = [];
for (const [index, key] of plugins.entries()) {
  const manifest = pluginFrontends[key];
  if (!manifest) continue;
  if (readPluginManifests()[key].source_layout === "contained") {
    const ownSource = pluginSourcePath(key, "miniprogram/src");
    if (existsSync(ownSource)) {
      cpSync(ownSource, generatedInput, { recursive: true });
      if (process.argv[2] !== "build")
        pluginWatchers.push(
          watch(ownSource, { recursive: true }, (_event, filename) => {
            if (filename) copySourceFile(String(filename), ownSource);
          }),
        );
    }
  }
  const directory = join(projectRoot, "..", "..", key, "miniprogram");
  const target = join(generatedInput, "plugins", key, "miniprogram");
  mkdirSync(dirname(target), { recursive: true });
  const providerOptions = {
    recursive: true,
    filter: (path) => relative(directory, path).split(sep)[0] !== "src",
  };
  cpSync(directory, target, providerOptions);
  const importPath = `../plugins/${key}/${manifest.miniapp_service_provider.replace(/\.ts$/, "")}`;
  providerImports.push(
    `import * as provider${index} from ${JSON.stringify(importPath)};`,
  );
  providerDefinitions.push(
    `{ ...provider${index}, key: ${JSON.stringify(key)} }`,
  );
  if (process.argv[2] !== "build")
    pluginWatchers.push(
      watch(directory, { recursive: true }, () =>
        cpSync(directory, target, providerOptions),
      ),
    );
}
writeFileSync(
  join(generatedInput, "config/pluginProviders.ts"),
  `import type { MiniappServiceProvider } from "./pluginServices";\n${providerImports.join("\n")}\nexport const pluginProviders: MiniappServiceProvider[] = [${providerDefinitions.join(",")}];\n`,
);
console.log(`小程序部署组合：${profile}，页面 ${selectedPaths.size} 个`);
writeFileSync(
  join(generatedInput, "tsconfig.json"),
  JSON.stringify(
    {
      extends: "../../tsconfig.json",
      compilerOptions: {
        baseUrl: ".",
        paths: { "@/*": ["./*"], "@plugins/*": ["../../../../../plugins/*"], "@product-branding": ["../../../../../product-branding.d.ts"] },
      },
      include: ["main.ts", "deployment.d.ts", "pages/**/*.vue"],
    },
    null,
    2,
  ),
);
if (prepareOnly) {
  pluginWatchers.forEach((watcher) => watcher.close());
  process.exit(0);
}

const cli = join(
  projectRoot,
  "node_modules",
  "@dcloudio",
  "vite-plugin-uni",
  "bin",
  "uni.js",
);
const child = spawn(process.execPath, [cli, ...args], {
  cwd: projectRoot,
  env: { ...process.env, UNI_INPUT_DIR: generatedInput },
  stdio: "inherit",
});

let watcher;
if (args[0] !== "build") {
  watcher = watch(sourceRoot, { recursive: true }, (_event, filename) => {
    if (!filename) return;
    const path = String(filename);
    if (
      path === "pages.json" ||
      path.replaceAll(sep, "/") === "config/pluginProviders.ts"
    )
      return;
    try {
      copySourceFile(path);
    } catch (error) {
      console.error(`同步小程序页面失败：${path}`, error);
    }
  });
}

child.on("exit", (code, signal) => {
  watcher?.close();
  pluginWatchers.forEach((watcher) => watcher.close());
  rmSync(generatedInput, { recursive: true, force: true, maxRetries: 5, retryDelay: 100 });
  if (signal) process.kill(process.pid, signal);
  else process.exitCode = code ?? 1;
});
for (const signal of ["SIGINT", "SIGTERM"]) {
  process.on(signal, () => child.kill(signal));
}
