function pad(value: number) {
  return String(value).padStart(2, "0");
}

export function formatLocalDateTime(value?: string | null) {
  if (!value) return "—";
  const clean = value.trim();
  if (!/(?:Z|[+-]\d{2}:\d{2})$/i.test(clean)) {
    return clean.replace("T", " ").slice(0, 16);
  }
  const timestamp = Date.parse(clean);
  if (!Number.isFinite(timestamp)) {
    return clean.replace("T", " ").slice(0, 16);
  }
  // 带时区的接口时间交由设备转换；旧的无时区展示值沿用上面的兼容处理。
  const local = new Date(timestamp);
  return `${local.getFullYear()}-${pad(local.getMonth() + 1)}-${pad(local.getDate())} ${pad(local.getHours())}:${pad(local.getMinutes())}`;
}
