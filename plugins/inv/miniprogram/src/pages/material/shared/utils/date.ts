export function pad(value: number) {
  return String(value).padStart(2, "0");
}

export function dateKey(date = new Date()) {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

export function dateTimeText(date = new Date()) {
  return `${dateKey(date)} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

export function timeText(date = new Date()) {
  return `${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

export function addDays(offset: number) {
  const date = new Date();
  date.setDate(date.getDate() + offset);
  return dateKey(date);
}

export function dayCount(start: string, end: string) {
  const startTime = new Date(`${start}T00:00:00`).getTime();
  const endTime = new Date(`${end}T00:00:00`).getTime();
  if (
    !Number.isFinite(startTime) ||
    !Number.isFinite(endTime) ||
    endTime < startTime
  )
    return 0;
  return Math.floor((endTime - startTime) / 86400000) + 1;
}

export function friendlyDate(value: string) {
  const date = new Date(`${value}T00:00:00`);
  if (Number.isNaN(date.getTime())) return value;
  const weekdays = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"];
  return `${date.getMonth() + 1}月${date.getDate()}日 ${weekdays[date.getDay()]}`;
}

export function uid(prefix: string) {
  return `${prefix}-${Date.now().toString(36).toUpperCase()}-${Math.random().toString(36).slice(2, 6).toUpperCase()}`;
}
