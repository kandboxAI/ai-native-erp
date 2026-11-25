import { createRequire } from "node:module";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

export const name = "erp-server-time-context";
export const inject = ["agents"];

/** 每轮首个请求提供时间，轮内跨日时更新；业务日期不依赖浏览器时区。 */
export function createTimeContextHook(createUserMessage, timeZone = "Asia/Shanghai") {
  const formatter = new Intl.DateTimeFormat("zh-CN", {
    timeZone,
    year: "numeric", month: "2-digit", day: "2-digit", weekday: "long",
    hour: "2-digit", minute: "2-digit", second: "2-digit",
    hourCycle: "h23", timeZoneName: "longOffset",
  });
  const latest = new WeakMap();

  return async ({ agent, turn, signal }, next) => {
    const decision = await next();
    if (decision.kind === "reject" || signal.aborted) return decision;

    const parts = Object.fromEntries(formatter.formatToParts(Date.now()).map(part => [part.type, part.value]));
    const date = `${parts.year}-${parts.month}-${parts.day}`;
    const previous = latest.get(agent.session);
    if (previous?.turn === turn && previous.date === date) return decision;

    const offset = parts.timeZoneName.replace(/^GMT$/, "GMT+00:00").slice(3);
    const timestamp = `${date}T${parts.hour}:${parts.minute}:${parts.second}${offset}`;
    const text = [
      "【服务端时间上下文】",
      `当前时间：${timestamp}[${timeZone}]。`,
      `今天：${date}，${parts.weekday}。`,
      `ERP 业务时区：${timeZone}。今天、明天、本周、下周等相对日期以最新的服务端时间上下文为基准；自然周从星期一开始。`,
      "用户明确指定日期或时区时按其指定解释；调用日期相关接口时传入明确日期，并在回答中注明查询日期。",
    ].join("\n");
    const message = createUserMessage({
      content: [{ type: "text", text }],
      source: { kind: name, form: "snapshot", sections: [{ name, text }] },
    });
    latest.set(agent.session, { turn, date });
    return { ...decision, messages: [...decision.messages, message] };
  };
}

export async function apply(ctx, config = {}) {
  // 插件位于 ERP，消息工厂从当前 DSH 启动仓库解析，复用同一运行时的消息契约。
  const require = createRequire(resolve(process.cwd(), "apps/cli/package.json"));
  const { createUserMessage } = await import(pathToFileURL(require.resolve("@deepseek-ai/dsh-llm")).href);
  ctx.on("agent/pre-step", createTimeContextHook(createUserMessage, config.timeZone), { prepend: true });
}
