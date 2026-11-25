import { defineConfig, loadEnv } from "vite";
import uni from "@dcloudio/vite-plugin-uni";
import { existsSync, readFileSync } from "node:fs";
import { relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { readDeployment } from "../../../deployment.mjs";
import {
  getProductBranding,
  productBrandingHtml,
} from "../../../product-branding.mjs";
import {
  selectMiniappPages,
  miniappPageOwner,
  miniappPages,
} from "../../../frontend-deployment.mjs";
import { validateWeixinApiBaseUrl } from "./scripts/weixin-release.mjs";
import { weixinUnusedModuleCleanup } from "./scripts/weixin-packages.mjs";
import { markdownItEntry } from "./scripts/markdown-it-entry.mjs";

const deployment = readDeployment();
const branding = getProductBranding(deployment.plugins);
const projectRoot = fileURLToPath(new URL(".", import.meta.url));
const pagesPath = fileURLToPath(new URL("./src/pages.json", import.meta.url));
const pages = selectMiniappPages(
  JSON.parse(readFileSync(pagesPath, "utf8")),
  deployment.plugins,
);

function deploymentInputHtmlEntry() {
  return {
    name: "deployment-input-html-entry",
    transformIndexHtml: {
      order: "pre" as const,
      handler(html: string) {
        const inputDir = process.env.UNI_INPUT_DIR;
        if (!inputDir) return html;

        const mainFile = ["main.ts", "main.js"].find((file) =>
          existsSync(resolve(inputDir, file)),
        );
        if (!mainFile) {
          throw new Error(
            `小程序构建输入目录缺少 main.ts/main.js：${inputDir}`,
          );
        }

        const mainPath = relative(
          projectRoot,
          resolve(inputDir, mainFile),
        ).replaceAll("\\", "/");
        if (mainPath === ".." || mainPath.startsWith("../")) {
          throw new Error(`小程序构建输入目录不在项目目录内：${inputDir}`);
        }

        const targetEntry = `/${mainPath}`;
        if (
          html.includes(`src="${targetEntry}"`) ||
          html.includes(`src='${targetEntry}'`)
        ) {
          return html;
        }

        const rewritten = html.replace(
          /(<script\b[^>]*\bsrc=["'])\/src\/main\.(?:ts|js)(["'][^>]*>)/i,
          `$1${targetEntry}$2`,
        );
        if (rewritten === html) {
          throw new Error(
            "index.html 未找到 /src/main.ts 或 /src/main.js 入口",
          );
        }
        return rewritten;
      },
    },
  };
}

export default defineConfig(({ mode }) => {
  if (
    process.env.UNI_PLATFORM === "mp-weixin" &&
    process.env.NODE_ENV === "production"
  ) {
    validateWeixinApiBaseUrl(
      loadEnv(mode, projectRoot, "VITE_").VITE_API_BASE_URL,
    );
  }
  return {
    plugins: [
      deploymentInputHtmlEntry(),
      uni(),
      productBrandingHtml(branding),
      weixinUnusedModuleCleanup(),
    ],
    define: {
      __PRODUCT_BRANDING__: JSON.stringify(branding),
      __DEPLOYMENT_PROFILE__: JSON.stringify(deployment.profile),
      __DEPLOYED_MINIAPP_PAGES__: JSON.stringify(
        miniappPages(pages).map((page) => `/${page.path}`),
      ),
      __MINIAPP_TAB_PAGES__: JSON.stringify(
        pages.tabBar?.list.map((item) => `/${item.pagePath}`) || [],
      ),
      __MINIAPP_PAGE_OWNERS__: JSON.stringify(
        Object.fromEntries(
          miniappPages(pages).map((page) => [
            `/${page.path}`,
            miniappPageOwner(page.path),
          ]),
        ),
      ),
    },
    resolve: {
      // uni-app requires every page/component to remain inside UNI_INPUT_DIR.
      // Resolve plugin imports to their assembled copy, not the external source tree.
      alias: Object.fromEntries([
        // uni-app preserves symlinks; resolve MarkdownIt's own dependencies
        // from its installed pnpm package, not the top-level symlink directory.
        ["markdown-it", markdownItEntry],
        ...deployment.plugins.map((key) => [
          `@plugins/${key}/miniprogram/src`,
          process.env.UNI_INPUT_DIR || resolve(projectRoot, "src"),
        ]),
        ["@plugins", resolve(projectRoot, "../..")],
      ]),
      dedupe: ["vue", "@vue/shared"],
    },
  };
});
