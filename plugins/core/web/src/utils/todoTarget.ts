import type { Router } from "vue-router";
import type { TodoRow } from "@/api/todo";

/** 跳转到当前账号已由授权菜单注册的业务页面；不因收到待办注册新路由。 */
export async function openTodoTarget(router: Router, item: TodoRow) {
  const target = item.targets?.web || item.path;
  if (!target)
    throw new Error(
      item.web_unavailable_reason || "当前账号没有可用的业务办理入口"
    );
  if (!target.startsWith("/") || target.startsWith("//"))
    throw new Error("待办办理地址无效");
  const resolved = router.resolve(target);
  if (!resolved.matched.length || resolved.name === "PageNotFound")
    throw new Error(
      "当前账号未加载该业务的授权菜单，请刷新登录状态或联系管理员核对权限"
    );
  return router.push(target);
}
