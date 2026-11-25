import type { App } from "vue";
import type { Router } from "vue-router";
import { getHttpErrorMessage } from "@/utils/http/index";
import { message } from "@/utils/message";

/** 只为教务、财务页面兜底处理未捕获的异步错误，不改变其他业务页面。 */
export function installAcademicFinanceFeedback(app: App, router: Router) {
  const shown = new WeakSet<object>();
  function notify(error: unknown) {
    if (!router.currentRoute.value.meta.businessErrorFeedback) return false;
    if (error === "cancel" || error === "close") return false;
    if (error && typeof error === "object") {
      if ((error as { code?: string }).code === "ERR_CANCELED") return false;
      if (shown.has(error)) return true;
      shown.add(error);
    }
    message(getHttpErrorMessage(error, "操作失败，请稍后重试"), {
      type: "error",
      duration: 6000,
      showClose: true,
      grouping: true
    });
    return true;
  }
  const previous = app.config.errorHandler;
  app.config.errorHandler = (error, instance, info) => {
    notify(error);
    if (previous) previous(error, instance, info);
    else console.error(error);
  };
  window.addEventListener("unhandledrejection", event => {
    if (notify(event.reason)) event.preventDefault();
  });
}
