import { getPluginsList } from "./build/plugins.ts";
import postcssConfig from "./postcss.config.js";
import { readDeployment } from "../../../deployment.mjs";
import {
  getProductBranding,
  loginStepIcons,
  productBrandingHtml
} from "../../../product-branding.mjs";
import remixIcons from "@iconify/json/json/ri.json" with { type: "json" };
import { deploymentViews } from "./build/deploymentViews.ts";
import { pluginDependencies } from "./build/pluginDependencies.ts";
import { pluginWebSourceRoots } from "../../../plugin-sources.mjs";
import { include, exclude } from "./build/optimize.ts";
import { type UserConfigExport, type ConfigEnv, loadEnv } from "vite";
import {
  root,
  alias,
  wrapperEnv,
  pathResolve,
  __APP_INFO__
} from "./build/utils.ts";

export default async ({ mode }: ConfigEnv): Promise<UserConfigExport> => {
  const deployment = readDeployment();
  const branding = getProductBranding(deployment.plugins);
  const { VITE_CDN, VITE_PORT, VITE_COMPRESSION, VITE_PUBLIC_PATH } =
    wrapperEnv(loadEnv(mode, root));
  const agentRuntimeEnv = loadEnv(mode, root, "");
  const agentRuntimeApiTarget =
    agentRuntimeEnv.VITE_AGENT_RUNTIME_API_TARGET || "http://127.0.0.1:8000";
  const apiBaseUrl =
    agentRuntimeEnv.VITE_API_BASE_URL || "http://127.0.0.1:8000";
  const devHost =
    process.env.VITE_DEV_HOST || agentRuntimeEnv.VITE_DEV_HOST || "0.0.0.0";
  const usePolling =
    process.env.VITE_USE_POLLING === "true" ||
    agentRuntimeEnv.VITE_USE_POLLING === "true";
  const disableWatch =
    process.env.VITE_DISABLE_WATCH === "true" ||
    agentRuntimeEnv.VITE_DISABLE_WATCH === "true";
  const agentRuntimeTargetHasBaseEnv =
    agentRuntimeEnv.VITE_AGENT_RUNTIME_API_TARGET_HAS_BASE_ENV === "true";
  const pluginRoots = pluginWebSourceRoots(deployment.plugins);
  return {
    base: VITE_PUBLIC_PATH,
    root,
    resolve: {
      alias,
      // contained 插件从宿主解析共享运行时与图标依赖。
      dedupe: ["vue", "vue-router", "pinia", "@element-plus/icons-vue"]
    },
    // 显式加载并跟踪 PostCSS 配置及字号插件，避免开发服务继续缓存旧样式规则。
    css: {
      postcss: postcssConfig
    },
    // 服务端渲染
    server: {
      fs: { allow: [root, ...pluginRoots] },
      // 端口号
      port: VITE_PORT,
      host: devHost,
      // 文件监听耗尽时可用 VITE_USE_POLLING=true 降低系统 watcher 压力。
      // 受限开发环境可完全关闭 watcher；页面仍可访问，修改代码后手动重启即可。
      watch: disableWatch
        ? null
        : usePolling
          ? { usePolling: true, interval: 800 }
          : undefined,
      // 本地跨域代理 https://cn.vitejs.dev/config/server-options.html#server-proxy
      proxy: {
        "/api": {
          target: apiBaseUrl,
          changeOrigin: true
        },
        "/ed/api": {
          target: agentRuntimeApiTarget,
          changeOrigin: true,
          rewrite: path =>
            agentRuntimeTargetHasBaseEnv
              ? path
              : path.replace(/^\/ed\/api/, "/api")
        }
      },
      // 预热文件以提前转换和缓存结果，降低启动期间的初始页面加载时长并防止转换瀑布
      warmup: {
        clientFiles: ["./index.html", "./src/{views,components}/*"]
      }
    },
    plugins: [
      pluginDependencies(pluginWebSourceRoots(deployment.plugins)),
      productBrandingHtml(branding),
      deploymentViews(deployment.plugins),
      ...(await getPluginsList(VITE_CDN, VITE_COMPRESSION))
    ],
    // https://cn.vitejs.dev/config/dep-optimization-options.html#dep-optimization-options
    optimizeDeps: {
      include,
      exclude
    },
    build: {
      manifest: true,
      // https://cn.vitejs.dev/guide/build.html#browser-compatibility
      target: "es2015",
      sourcemap: false,
      // 消除打包大小超过500kb警告
      chunkSizeWarningLimit: 4000,
      rolldownOptions: {
        input: {
          index: pathResolve("./index.html", import.meta.url)
        },
        // 静态资源分类打包
        output: {
          chunkFileNames: "static/js/[name]-[hash].js",
          entryFileNames: "static/js/[name]-[hash].js",
          assetFileNames: "static/[ext]/[name]-[hash].[ext]"
        },
        checks: {
          pluginTimings: false,
          toleratedTransform: false
        }
      }
    },
    define: {
      __INTLIFY_PROD_DEVTOOLS__: false,
      __DEPLOYMENT_PROFILE__: JSON.stringify(deployment.profile),
      __PRODUCT_BRANDING__: JSON.stringify(branding),
      __LOGIN_STEP_ICONS__: JSON.stringify(loginStepIcons(branding.login.steps, remixIcons)),
      __APP_INFO__: JSON.stringify(__APP_INFO__)
    }
  };
};
