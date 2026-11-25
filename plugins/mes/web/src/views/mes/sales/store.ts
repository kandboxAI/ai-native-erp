import { defineStore } from "pinia";
import { markRaw, reactive, watch } from "vue";
import { store } from "@/store";
import { getToken, hasPerms } from "@/utils/auth";
import { useUserStoreHook } from "@/store/modules/user";
import { createDemoState, saveQuote, type Quote } from "./model";
import {
  createAiQuoteTasks,
  advanceAiQuoteTasks,
  updateAiQuoteCost,
  suggestAiPrice,
  adoptAiQuote,
  rejectAiQuote,
} from "./aiQuoteModel";
import { LocalDrawings } from "./files";
import { createSalesOperationCatalog } from "./operationCatalog";

// 前端适配阶段共享同一份数据；不持久化到浏览器，不调用真实订单接口。
export const useMesSalesStore = defineStore("mes-sales-front", () => {
  const state = reactive(createDemoState());
  // 新建单据跨整页路由传递；不列为已保存记录，也不持久化。
  const quoteDrafts = reactive<Record<string, Quote>>({});
  const files = markRaw(new LocalDrawings());
  const operationCatalog = markRaw(createSalesOperationCatalog());
  const principal = useUserStoreHook();
  let owner = getToken()?.userId || "";
  let aiTimer: ReturnType<typeof setInterval> | undefined;
  function requireEngineering() {
    ensureSession();
    if (!hasPerms("mes:quotation:list") || !hasPerms("mes:quotation:price"))
      throw Error("缺少工程报价权限");
  }
  function saveEngineeringDraft(draft: Quote) {
    requireEngineering();
    return saveQuote(state, draft, "save", "engineering");
  }
  function startAiQuotes(draft: Quote, lineIds: string[], rerun = false) {
    saveEngineeringDraft(draft);
    const tasks = createAiQuoteTasks(state, draft.id, lineIds, rerun);
    advanceAiQuoteTasks(state);
    if (!aiTimer)
      aiTimer = setInterval(() => {
        if (!hasPerms("mes:quotation:price")) {
          state.ai_quote_tasks
            .filter((task) => ["running", "queued"].includes(task.status))
            .forEach((task) => {
              task.status = "failed";
              task.error = "当前账号已失去工程报价权限";
            });
        } else advanceAiQuoteTasks(state);
        if (
          !state.ai_quote_tasks.some((task) =>
            ["running", "queued"].includes(task.status),
          )
        ) {
          clearInterval(aiTimer);
          aiTimer = undefined;
        }
      }, 650);
    return tasks;
  }
  function retryAiQuote(id: string) {
    requireEngineering();
    const task = state.ai_quote_tasks.find((row) => row.id === id);
    const quote = state.quotes.find((row) => row.id === task?.quote_id);
    if (!task || !quote) throw Error("报价记录不存在或暂存数据已清空");
    return startAiQuotes(quote, [task.line_id], true)[0];
  }
  function updateAiCost(id: string) {
    requireEngineering();
    return updateAiQuoteCost(state, id);
  }
  function suggestPrice(id: string) {
    requireEngineering();
    return suggestAiPrice(state, id);
  }
  function adoptAi(id: string, confirmed: boolean) {
    requireEngineering();
    return adoptAiQuote(state, id, confirmed);
  }
  function rejectAi(id: string, reason: string) {
    requireEngineering();
    return rejectAiQuote(state, id, reason);
  }
  function reset() {
    clearInterval(aiTimer);
    aiTimer = undefined;
    files.clear();
    operationCatalog.reset();
    Object.keys(quoteDrafts).forEach((key) => delete quoteDrafts[key]);
    Object.assign(state, createDemoState());
  }
  function ensureSession() {
    const next = getToken()?.userId || "";
    if (next !== owner) {
      reset();
      owner = next;
    }
  }
  watch(
    () => [principal.username, principal.permissions.length],
    () => {
      if (!principal.username || !principal.permissions.length) {
        reset();
        owner = "";
      } else ensureSession();
    },
    { flush: "sync" },
  );
  return {
    state,
    files,
    quoteDrafts,
    operationCatalog,
    ensureSession,
    saveEngineeringDraft,
    startAiQuotes,
    retryAiQuote,
    updateAiCost,
    suggestPrice,
    adoptAi,
    rejectAi,
  };
});
export function useMesSalesStoreHook() {
  const current = useMesSalesStore(store);
  current.ensureSession();
  return current;
}
