import type { MesTask } from "@plugins/mes/web/src/api/mes";

const dayFormatter = new Intl.DateTimeFormat("en-CA", {
  timeZone: "Asia/Shanghai",
  year: "numeric",
  month: "2-digit",
  day: "2-digit"
});

export function shiftDay(day: string, delta: number): string {
  const value = new Date(`${day}T00:00:00Z`);
  if (
    !/^\d{4}-\d{2}-\d{2}$/.test(day) ||
    !Number.isFinite(+value) ||
    value.toISOString().slice(0, 10) !== day
  )
    throw Error("请选择有效日期");
  value.setUTCDate(value.getUTCDate() + delta);
  return value.toISOString().slice(0, 10);
}
export function today(): string {
  const parts = dayFormatter.formatToParts(new Date());
  const value = (key: string) => parts.find(item => item.type === key)?.value;
  return `${value("year")}-${value("month")}-${value("day")}`;
}
export function scheduleDays(period: string[]): string[] {
  if (period.length !== 2) throw Error("请选择完整的时间轴显示区间");
  const [start, end] = period;
  shiftDay(start, 0);
  shiftDay(end, 0);
  const length =
    (+new Date(`${end}T00:00:00Z`) - +new Date(`${start}T00:00:00Z`)) /
      86400000 +
    1;
  if (length < 1 || length > 31)
    throw Error("时间轴须为正向区间，一次最多显示 31 天");
  return Array.from({ length }, (_, index) => shiftDay(start, index));
}
export function overlapMinutes(
  start: string | null | undefined,
  end: string | null | undefined,
  day: string
): number {
  if (!start || !end) return 0;
  const first = +new Date(`${day}T00:00:00+08:00`),
    last = first + 86400000;
  const a = +new Date(start),
    b = +new Date(end);
  return Number.isFinite(a) && Number.isFinite(b)
    ? Math.max(0, Math.min(b, last) - Math.max(a, first)) / 60000
    : 0;
}
export function duration(minutes: number): string {
  const amount = Math.max(0, Math.round(Number(minutes) || 0));
  return `${Math.floor(amount / 60)}时${amount % 60}分`;
}
export function progress(row: MesTask): number {
  return row.planned_quantity > 0
    ? Math.min(
        100,
        Math.max(
          0,
          Math.round(
            ((row.good_quantity + row.scrap_quantity + row.rework_quantity) /
              row.planned_quantity) *
              100
          )
        )
      )
    : 0;
}
export function canSchedule(
  row: Pick<MesTask, "status_code" | "work_order_status_code">
): boolean {
  return (
    ["draft", "pending", "dispatched"].includes(row.status_code) &&
    ["draft", "released", "in_progress"].includes(
      row.work_order_status_code || ""
    )
  );
}

export type ScheduleWorkOrder = {
  id: string;
  first: MesTask;
  tasks: MesTask[];
  completed: number;
  scheduled: number;
  canAutoSchedule: boolean;
};

export function scheduleWorkOrders(rows: MesTask[]): ScheduleWorkOrder[] {
  const groups = new Map<string, MesTask[]>();
  for (const row of rows) {
    if (!groups.has(row.work_order_id)) groups.set(row.work_order_id, []);
    groups.get(row.work_order_id)!.push(row);
  }
  return [...groups.entries()].map(([id, items]) => {
    const tasks = [...items].sort(
      (a, b) => a.sequence_no - b.sequence_no || a.id.localeCompare(b.id)
    );
    return {
      id,
      first: tasks[0],
      tasks,
      completed: tasks.filter(row => row.status_code === "completed").length,
      scheduled: tasks.filter(row => row.planned_start_at && row.planned_end_at)
        .length,
      canAutoSchedule:
        ["released", "in_progress"].includes(
          tasks[0].work_order_status_code || ""
        ) && tasks.some(canSchedule)
    };
  });
}

export function automaticSelectionError(rows: MesTask[]): string {
  if (!rows.length) return "请先选择货品工单";
  if (new Set(rows.map(row => row.org_id)).size !== 1)
    return "请选择同一组织的货品工单";
  if (new Set(rows.map(row => row.work_order_id)).size > 10)
    return "一次最多选择10张货品工单";
  return "";
}
export function continuousPeriods<
  T extends { work_order_no: string; sequence_no: number; period: Date[] }
>(rows: T[], start: Date | string, hours: number, gap: number): T[] {
  let cursor = +new Date(start);
  if (
    !Number.isFinite(cursor) ||
    !Number.isFinite(hours) ||
    hours <= 0 ||
    !Number.isFinite(gap) ||
    gap < 0
  )
    throw Error("请填写有效的开始时间、正数工序时长和非负间隔");
  return [...rows]
    .sort(
      (left, right) =>
        left.work_order_no.localeCompare(right.work_order_no) ||
        left.sequence_no - right.sequence_no
    )
    .map(row => {
      const end = cursor + hours * 3600000;
      const result = { ...row, period: [new Date(cursor), new Date(end)] };
      cursor = end + gap * 60000;
      return result;
    });
}
export function periodOnDay(row: MesTask, day: string): Date[] {
  const length =
    row.planned_start_at && row.planned_end_at
      ? +new Date(row.planned_end_at) - +new Date(row.planned_start_at)
      : 3600000;
  const start = +new Date(`${day}T09:00:00+08:00`);
  return [new Date(start), new Date(start + Math.max(60000, length))];
}
