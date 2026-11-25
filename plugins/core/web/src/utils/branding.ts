/** 品牌资源与 Vite 部署前缀一致；客户可配置本站静态路径或 HTTPS 地址。 */
export function brandingAssetUrl(path: string) {
  if (!path) return "";
  if (path.startsWith("https://")) return path;
  return new URL(
    path.replace(/^\/+/, ""),
    new URL(import.meta.env.BASE_URL, location.origin)
  ).href;
}
