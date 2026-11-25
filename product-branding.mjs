import { readFileSync, realpathSync } from "node:fs";
import { isAbsolute, join, relative, sep } from "node:path";
import { readPluginFrontends, repositoryRoot } from "./plugin-frontends.mjs";
import { validateBranding } from "./branding-schema.mjs";

function mergeBranding(...layers) {
  return layers.reduce((result, layer) => ({
    ...result, ...layer, login: { ...result.login, ...layer?.login },
  }), {});
}

function validateProfile(profile, name, frontends) {
  if (!profile || typeof profile !== "object" || Array.isArray(profile) ||
    Object.keys(profile).sort().join(",") !== "branding,plugin_key" ||
    typeof profile.plugin_key !== "string" || !Object.hasOwn(frontends, profile.plugin_key))
    throw new Error(`客户展示方案无效：${name}`);
  validateBranding(profile.branding, name);
}

function isOutside(root, file) {
  const path = relative(root, file);
  return path === ".." || path.startsWith(`..${sep}`) || isAbsolute(path);
}

function readProfileFile(name, root) {
  // 名称已经过校验，统一按约定目录读取，不再维护第二份名称到文件的映射。
  const reference = `branding/profiles/${name}.json`;
  const path = join(root, reference);
  let source;
  try {
    const realPath = realpathSync(path);
    if (isOutside(realpathSync(root), realPath))
      throw new Error(`客户展示方案 ${name} 的文件不能通过链接指向项目外`);
    source = readFileSync(realPath, "utf8");
  } catch (error) {
    if (error.code === "ENOENT")
      throw new Error(`客户展示方案 ${name} 的配置文件不存在：${reference}`);
    throw error;
  }
  try {
    return JSON.parse(source);
  } catch {
    throw new Error(`客户展示方案 ${name} 的配置文件不是有效 JSON：${reference}`);
  }
}

/** 公共默认值与客户差异按字段合并；客户方案只对其绑定的部署插件生效。 */
export function getProductBranding(plugins, root = repositoryRoot) {
  const definitions = JSON.parse(readFileSync(join(root, "product-branding.json"), "utf8"));
  const frontends = readPluginFrontends(root);
  if (!definitions || typeof definitions !== "object" || Array.isArray(definitions))
    throw new Error("product-branding.json 格式无效");
  validateBranding(definitions.default, "default", { requireTitle: true });
  if (Object.hasOwn(definitions, "profiles"))
    throw new Error("展示方案放在 branding/profiles/<名称>.json，通过 ERP_BRANDING_PROFILE 选择");
  const selected = process.env.ERP_BRANDING_PROFILE ?? definitions.selected_profile;
  if (selected !== undefined && selected !== null &&
    (typeof selected !== "string" || selected === "null" || !/^[a-z][a-z0-9_]*$/.test(selected)))
    throw new Error("ERP_BRANDING_PROFILE 或 selected_profile 必须是小写 snake_case 配置名称");
  for (const [key, value] of Object.entries(definitions)) {
    if (["default", "selected_profile"].includes(key)) continue;
    if (!Object.hasOwn(frontends, key)) throw new Error(`品牌覆盖引用未知插件：${key}`);
    validateBranding(value, key);
  }
  const active = [...new Set(plugins)].filter(key => key !== "default");
  // 外置文件只在选中时读取，公共部署无需准备未选客户的私有配置。
  const profile = selected ? readProfileFile(selected, root) : undefined;
  if (profile) validateProfile(profile, selected, frontends);
  const applicable = profile && active.includes(profile.plugin_key) ? profile : undefined;
  const candidates = active.filter(key => frontends[key]?.branding || definitions[key]);
  const key = applicable?.plugin_key ?? (candidates.length === 1 ? candidates[0] : undefined);
  const branding = mergeBranding({
    title: "综合管理系统", subtitle: "统一业务管理平台", english_name: "INTEGRATED MANAGEMENT SYSTEM",
    mark: "管", assistant_name: "业务助手", description: "统一业务入口，协同各项工作。",
    logo: "/logo.svg", header_logo: "", favicon: "/favicon.ico", miniapp_logo: "", miniapp_assistant_avatar: "",
  }, definitions.default, frontends[key]?.branding, definitions[key], applicable?.branding);
  // 客户图片失效时仍使用公共插件的图片，不再次落回客户覆盖值。
  branding.fallback_logo = frontends[key]?.branding?.logo || definitions.default.logo || "/logo.svg";
  branding.login = {
    school_name: branding.title, english_name: branding.english_name,
    welcome_title: "欢迎登录", subtitle: branding.subtitle, tagline: branding.description,
    background: "", background_alt: "", ai_note: "按岗位查询信息，重要操作由本人确认。",
    help_lines: ["账号由管理员统一分配。", "忘记密码请联系管理员。"], steps: [],
    ...branding.login,
  };
  return Object.freeze(branding);
}

/** 构建时只提取配置用到的图标，避免整套图标进入页面或运行时联网。 */
export function loginStepIcons(steps, collection) {
  return Object.fromEntries(steps.filter(step => step.icon).map(({ icon }) => {
    const data = collection.icons[icon.slice(3)];
    if (!data) throw new Error(`登录步骤图标不存在：${icon}`);
    return [icon, { width: collection.width, height: collection.height, ...data }];
  }));
}

/** HTML 初始标题与应用挂载后的标题同源，避免启动时闪现旧品牌。 */
export function productBrandingHtml(branding) {
  const escape = value => value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
  return {
    name: "product-branding-html",
    transformIndexHtml: {
      order: "post",
      handler: (html, context) => {
        const favicon = branding.favicon || "/favicon.ico";
        const href = /^https:\/\//.test(favicon) ? favicon :
          `${context?.base || "/"}${favicon.replace(/^\/+/, "")}`;
        return html.replace(/<title>[^<]*<\/title>/i, () => `<title>${escape(branding.title)}</title>`)
          .replace(/<link\b(?=[^>]*\brel=["']icon["'])[^>]*>/i,
            () => `<link rel="icon" href="${escape(href)}" />`);
      },
    },
  };
}
