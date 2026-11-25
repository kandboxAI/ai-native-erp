import type { CncProgress, Quote } from "./api";

export const CNC_POLL_INTERVAL = 4000;
export const hasPendingCnc = (quote: Quote) =>
  quote.lines.some((line) =>
    line.cnc_records?.some((record) =>
      ["queued", "running"].includes(record.status_code),
    ),
  );

type Target = { key: string; quote: Quote };

// Update task records only: prices, materials and optimistic versions belong to the form.
export function createCncProgressPoller(options: {
  target: () => Target | undefined;
  paused: () => boolean;
  fetch: (id: string) => Promise<CncProgress>;
  notify: (message: string) => void;
}) {
  let timer: ReturnType<typeof setTimeout> | undefined;
  let inFlight = false;
  let disposed = false;
  let epoch = 0;
  let blockedKey: string | undefined;

  function schedule() {
    clearTimeout(timer);
    timer = undefined;
    const target = options.target();
    if (
      !disposed &&
      !inFlight &&
      target?.quote.id &&
      target.key !== blockedKey &&
      hasPendingCnc(target.quote)
    )
      timer = setTimeout(tick, CNC_POLL_INTERVAL);
  }

  async function tick() {
    timer = undefined;
    const target = options.target();
    if (
      disposed ||
      !target?.quote.id ||
      target.key === blockedKey ||
      !hasPendingCnc(target.quote)
    )
      return;
    if (options.paused()) {
      schedule();
      return;
    }
    const token = epoch;
    const current = () => {
      const latest = options.target();
      return (
        !disposed &&
        token === epoch &&
        latest?.key === target.key &&
        latest.quote === target.quote &&
        !options.paused()
      );
    };
    inFlight = true;
    try {
      const result = await options.fetch(target.quote.id);
      if (!current()) return;
      const records = new Map(
        result.lines.map((line) => [line.id, line.cnc_records]),
      );
      for (const line of target.quote.lines) {
        if (line.id && records.has(line.id))
          line.cnc_records = records.get(line.id);
      }
      options.notify("");
    } catch (error) {
      if (!current()) return;
      const status = (error as { status?: number }).status;
      if (status != null && [401, 403, 404].includes(status)) {
        blockedKey = target.key;
        options.notify("无法继续更新核价状态，请重新登录或确认访问权限");
      } else {
        options.notify("核价状态暂未更新，正在重试");
      }
    } finally {
      inFlight = false;
      schedule();
    }
  }

  return {
    sync() {
      epoch++;
      schedule();
    },
    dispose() {
      disposed = true;
      epoch++;
      clearTimeout(timer);
    },
  };
}
