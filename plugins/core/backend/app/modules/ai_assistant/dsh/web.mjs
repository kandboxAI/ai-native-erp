import { createRequire } from "node:module";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

export const name = "erp-server-web";
export const inject = ["tools", "systemPrompt"];

/** 保留 DSH 联网工具，搜索 Provider 直连 ERP 保护的官方 JSON 搜索出口。 */
export async function apply(ctx) {
  const require = createRequire(resolve(process.cwd(), "apps/cli/package.json"));
  const baseRequire = createRequire(require.resolve("@deepseek-ai/dsh-base/package.json"));
  const load = module => import(pathToFileURL(baseRequire.resolve(module)).href);
  const { default: WebRuntime, WebError } = await load("@deepseek-ai/dsh-web");
  const fetchPlugin = await load("@deepseek-ai/dsh-web-fetch-http");
  const toolsPlugin = await load("@deepseek-ai/dsh-tool-web");

  const token = process.env.ERP_SERVER_GATEWAY_TOKEN;
  const clientId = process.env.ERP_SERVER_CLIENT_ID;
  if (!token || !clientId) throw new Error("联网工具缺少当前用户的网关凭据");
  const searchUrl = new URL(`/api/llm-gateway/web-search/${clientId}/search`, process.env.ERP_SERVER_API_URL);
  const timeoutMs = Number(process.env.ERP_SERVER_TOOL_TIMEOUT_MS);
  await ctx.plugin(WebRuntime, { searchProvider: "erp-search-json", fetchProvider: "http" });
  // 短期凭据只在进程内交给插件，不写入生成 patch，也不把供应商 Key 交给 DSH。
  await ctx.plugin({
    name: "erp-search-json", inject: ["web"],
    apply(searchContext) {
      searchContext.web.registerSearchProvider({
        id: "erp-search-json", available: () => true,
        async search(request, signal) {
          const response = await fetch(searchUrl, {
            method: "POST", signal,
            headers: { "content-type": "application/json", "x-api-key": token },
            body: JSON.stringify({ query: request.query, count: request.maxResults ?? 5 }),
          });
          if (!response.ok) {
            const error = await response.json().catch(() => ({}));
            throw new WebError(typeof error.detail === "string" ? error.detail : `联网搜索未完成（HTTP ${response.status}）`, "WEB_PROVIDER_ERROR");
          }
          return await response.json();
        },
      });
    },
  });
  await ctx.plugin(fetchPlugin, {
    timeoutMs, maxBodyChars: Number(process.env.ERP_SERVER_MAX_RESPONSE_CHARS),
  });
  await ctx.plugin(toolsPlugin, {
    search: true, fetch: true, searchMaxResults: 5, searchMaxQueries: 3,
    searchTimeoutMs: timeoutMs, fetchTimeoutMs: timeoutMs,
    fetchMaxOutputChars: Number(process.env.ERP_SERVER_MAX_RESPONSE_CHARS),
  });
}
