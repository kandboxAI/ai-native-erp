export const name = "erp-server-knowledge";
export const inject = ["agents", "tools"];

export const READ_TOOLS = [
  "erp_discover", "erp_api", "erp_query",
  "erp_knowledge_search", "erp_knowledge_read_document",
  "web_search", "web_fetch",
];

// 与桌面端共用知识工具；网页和小程序不展示新建、改稿及提审工具。
export function apply(ctx) {
  ctx.on("agent/created", ({ agent }) => {
    agent.ctx.tools.restrict({ allow: READ_TOOLS });
  });
}
