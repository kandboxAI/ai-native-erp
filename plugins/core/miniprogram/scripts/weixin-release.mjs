import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { isIP } from "node:net";
import { join } from "node:path";
import { inspectWeixinPackages } from "./weixin-packages.mjs";

const WEIXIN_APPID = /^wx[0-9a-f]{16}$/;

export function resolveWeixinAppId(value, { release }) {
  const appid = (value || "").trim();
  if (!appid && !release) return "touristappid";
  if (!WEIXIN_APPID.test(appid))
    throw new Error("请在小程序环境配置中填写有效的 WEIXIN_APPID");
  return appid;
}

// 体验版与正式版均需要 HTTPS 域名，不能沿用本地开发地址。
export function validateWeixinApiBaseUrl(value) {
  const message =
    "微信发布构建需要有效的 VITE_API_BASE_URL：请在 .env.production 配置 HTTPS 服务器域名，并在微信公众平台登记 request 合法域名";
  let url;
  try {
    url = new URL(String(value || "").trim());
  } catch {
    throw new Error(message);
  }
  const hostname = url.hostname.toLowerCase().replace(/\.$/, "");
  if (
    url.protocol !== "https:" ||
    !hostname.includes(".") ||
    isIP(hostname) ||
    hostname.startsWith("[") ||
    /(^|\.)(localhost|local|test|invalid|example)$/.test(hostname) ||
    url.username ||
    url.password ||
    url.search ||
    url.hash
  ) {
    throw new Error(message);
  }
  return url.href.replace(/\/+$/, "");
}

// 本地按未压缩文件字节保守计量；上传后的最终大小仍以微信扫描为准。
export function inspectWeixinRelease(directory) {
  const app = JSON.parse(readFileSync(join(directory, "app.json"), "utf8"));
  const project = JSON.parse(
    readFileSync(join(directory, "project.config.json"), "utf8"),
  );
  const privatePath = join(directory, "project.private.config.json");
  const privateProject = existsSync(privatePath)
    ? JSON.parse(readFileSync(privatePath, "utf8"))
    : {};
  const settings = { ...project.setting, ...privateProject.setting };
  const subpackageRoots = (app.subPackages || app.subpackages || []).map(
    ({ root }) => root.replace(/^\/+|\/+$/g, "") + "/",
  );
  let mainPackageBytes = 0;
  let mediaBytes = 0;
  function inspect(relative = "") {
    for (const name of readdirSync(join(directory, relative))) {
      const path = relative ? `${relative}/${name}` : name;
      // 开发工具项目配置和 source map 不属于运行代码包。
      if (
        /^project\.(?:private\.)?config\.json$/.test(path) ||
        path.endsWith(".map")
      )
        continue;
      const entry = statSync(join(directory, path));
      if (entry.isDirectory()) {
        inspect(path);
        continue;
      }
      if (!subpackageRoots.some((root) => path.startsWith(root)))
        mainPackageBytes += entry.size;
      // 保守统计整个代码包，避免将资源搬进分包后漏检。
      if (/\.(?:png|jpe?g|gif|webp|bmp|svg|apng|avif|ico|mp3|wav|m4a|aac|ogg|flac|wma)$/i.test(path))
        mediaBytes += entry.size;
    }
  }
  inspect();
  const errors = [];
  if (!WEIXIN_APPID.test(project.appid || ""))
    errors.push("未配置实际微信 AppID");
  if (app.lazyCodeLoading !== "requiredComponents")
    errors.push("未启用组件按需注入");
  if (settings.minified !== true)
    errors.push("未启用上传 JS 压缩（含本地设置覆盖）");
  if (settings.urlCheck !== true)
    errors.push("未启用合法域名校验（含本地设置覆盖）");
  if (mediaBytes > 200 * 1024)
    errors.push(`图片和音频资源合计 ${(mediaBytes / 1024).toFixed(1)} KiB，超过 200 KiB，请压缩资源或使用远程资源`);
  const graph = inspectWeixinPackages(directory);
  if (graph.unusedMainJs.length)
    errors.push(`主包存在未使用的 JS：${graph.unusedMainJs.join("、")}`);
  if (graph.missingReferences.length)
    errors.push(`JS/组件引用缺失：${graph.missingReferences.join("；")}`);
  if (graph.crossPackageReferences.length)
    errors.push(`存在跨分包引用：${graph.crossPackageReferences.join("；")}`);
  if (errors.length) throw new Error(`微信发布检查失败：${errors.join("；")}`);
  return { mainPackageBytes, mediaBytes };
}
