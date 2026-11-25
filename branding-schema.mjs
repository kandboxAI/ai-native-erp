/** 品牌仅包含展示配置；不承载权限、业务开关或秘密。 */
export const brandTextFields = [
  "title", "subtitle", "english_name", "mark", "assistant_name", "description",
];
export const brandAssetFields = ["logo", "header_logo", "favicon", "miniapp_logo", "miniapp_assistant_avatar"];
const loginTextFields = [
  "school_name", "english_name", "welcome_title", "subtitle", "tagline", "background_alt", "ai_note",
];

const object = value => value !== null && typeof value === "object" && !Array.isArray(value);

export function isBrandAsset(value) {
  // 允许站点静态资源和 HTTPS 图片，拒绝脚本、协议相对地址和路径穿越。
  return typeof value === "string" && (value === "" || (
    value === value.trim() && !/[\s<>"'\\?#]/.test(value) &&
    !value.startsWith("//") && !value.split("/").includes("..") &&
    (/^https:\/\/[^/]+(?:\/.*)?$/.test(value) || !value.includes(":"))
  ));
}

export function validateBranding(value, source, { requireTitle = false } = {}) {
  const fail = () => { throw new Error(`${source}: branding 展示配置无效`); };
  if (!object(value) || (requireTitle && (typeof value.title !== "string" || !value.title.trim()))) fail();
  for (const [key, item] of Object.entries(value)) {
    if (brandTextFields.includes(key)) {
      if (typeof item !== "string" || !item.trim()) fail();
    } else if (brandAssetFields.includes(key)) {
      if (!isBrandAsset(item)) fail();
    } else if (key === "login") {
      if (!object(item)) fail();
      for (const [field, content] of Object.entries(item)) {
        if (loginTextFields.includes(field)) {
          if (typeof content !== "string" || !content.trim()) fail();
        } else if (field === "background") {
          if (!isBrandAsset(content)) fail();
        } else if (field === "help_lines") {
          if (!Array.isArray(content) || content.some(line => typeof line !== "string" || !line.trim())) fail();
        } else if (field === "steps") {
          if (!Array.isArray(content) || content.some(step => !object(step) ||
            Object.keys(step).some(key => !["title", "lines", "icon"].includes(key)) ||
            (Object.hasOwn(step, "icon") && (typeof step.icon !== "string" || !/^ri:[a-z0-9]+(?:-[a-z0-9]+)*$/.test(step.icon))) ||
            typeof step.title !== "string" || !step.title.trim() || !Array.isArray(step.lines) ||
            step.lines.some(line => typeof line !== "string" || !line.trim()))) fail();
        } else fail();
      }
    } else fail();
  }
}
