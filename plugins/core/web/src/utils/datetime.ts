import dayjs from "dayjs";

/**
 * 与后端 app.framework.datetime_local 对齐：
 * - 业务时间均为 Asia/Shanghai 墙钟
 * - 提交 API 使用无时区 ISO；勿再使用末尾 Z / toISOString()
 */

/** Element Plus el-date-picker value-format */
export const PICKER_DATETIME_FORMAT = "YYYY-MM-DDTHH:mm:ss";
export const PICKER_DATE_FORMAT = "YYYY-MM-DD";

/** 列表/详情展示（到分钟） */
export const DISPLAY_DATETIME_MINUTE_FMT = "YYYY-MM-DD HH:mm";

/** 列表/详情展示（到秒，与后端 format_display_datetime 一致） */
export const DISPLAY_DATETIME_SECOND_FMT = "YYYY-MM-DD HH:mm:ss";

const DISPLAY_WALL_CLOCK_RE = /^(\d{4}-\d{2}-\d{2} \d{2}:\d{2})/;

export function formatDate(value?: string | null, empty = ""): string {
  if (!value) return empty;
  const s = String(value).trim();
  const match = s.match(/^(\d{4}-\d{2}-\d{2})/);
  if (match) return match[1];
  const d = dayjs(value);
  return d.isValid() ? d.format(PICKER_DATE_FORMAT) : empty;
}

/**
 * 展示时间。后端已返回 ``YYYY-MM-DD HH:mm:ss`` 时原样取到分钟，避免 dayjs 当 UTC 再偏 8 小时。
 */
export function formatTime(value?: string | null, empty = ""): string {
  if (!value) return empty;
  const s = String(value).trim();
  const m = s.match(DISPLAY_WALL_CLOCK_RE);
  if (m) return m[1];
  const d = dayjs(value);
  return d.isValid() ? d.format(DISPLAY_DATETIME_MINUTE_FMT) : empty;
}

export function formatDateTime(value?: string | null, empty = ""): string {
  if (!value) return empty;
  const s = String(value).trim();
  if (/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(s)) return s;
  const d = dayjs(value);
  return d.isValid() ? d.format(DISPLAY_DATETIME_SECOND_FMT) : empty;
}

export function toApiDateTime(
  value?: string | Date | dayjs.Dayjs | null
): string | undefined {
  if (value == null || value === "") return undefined;
  const normalized =
    typeof value === "string" ? value.trim().replace(" ", "T") : value;
  const d = dayjs(
    normalized,
    ["YYYY-MM-DDTHH:mm:ss", "YYYY-MM-DD HH:mm:ss", "YYYY-MM-DD"],
    true
  );
  return d.isValid() ? d.format(PICKER_DATETIME_FORMAT) : undefined;
}

export function nowPickerDateTime(): string {
  return dayjs().format(PICKER_DATETIME_FORMAT);
}

export function todayPickerDate(): string {
  return dayjs().format(PICKER_DATE_FORMAT);
}

export function toPickerDate(
  value?: string | Date | dayjs.Dayjs | null
): string | undefined {
  if (value == null || value === "") return undefined;
  const d = dayjs(value);
  return d.isValid() ? d.format(PICKER_DATE_FORMAT) : undefined;
}

export function toPickerDateTime(
  value?: string | Date | dayjs.Dayjs | null
): string | undefined {
  if (value == null || value === "") return undefined;
  const d = dayjs(value);
  return d.isValid() ? d.format(PICKER_DATETIME_FORMAT) : undefined;
}

export function buildBusinessDateTime(dateYmd: string): string {
  const d = dayjs(dateYmd, "YYYY-MM-DD");
  if (!d.isValid()) {
    return toPickerDateTime(dayjs()) ?? dayjs().format(PICKER_DATETIME_FORMAT);
  }
  if (dateYmd === dayjs().format("YYYY-MM-DD")) {
    return (
      toPickerDateTime(dayjs()) ??
      d.startOf("day").format(PICKER_DATETIME_FORMAT)
    );
  }
  return d.startOf("day").format(PICKER_DATETIME_FORMAT);
}

export function combineDateAndClock(
  date: string,
  clock: string
): string | undefined {
  const d = (date || "").trim();
  const c = (clock || "").trim();
  if (!d || !c) return undefined;
  return toApiDateTime(`${d}T${c}`);
}

export function splitPickerDateTime(value?: string | null): {
  date: string;
  clock: string;
} {
  if (value == null || value === "") return { date: "", clock: "" };
  const d = dayjs(String(value).trim().replace(" ", "T"));
  if (!d.isValid()) return { date: "", clock: "" };
  return {
    date: d.format("YYYY-MM-DD"),
    clock: d.format("HH:mm:ss")
  };
}

export function toDateRangeQuery(range?: [string, string] | null): {
  start?: string;
  end?: string;
} {
  if (!range?.[0]) return {};
  return {
    start: `${range[0]}T00:00:00`,
    end: range[1] ? `${range[1]}T23:59:59` : undefined
  };
}
