export function apiErrorMessage(err: unknown): string {
  const e = err as {
    message?: string;
    response?: { data?: { detail?: unknown; message?: unknown } };
  };
  const msg = e.response?.data?.message;
  if (typeof msg === "string" && msg.trim()) return msg;
  const d = e.response?.data?.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) {
    return (
      d
        .map((x: { msg?: string }) => x.msg ?? "")
        .filter(Boolean)
        .join("; ") || "请求失败"
    );
  }
  if (typeof e.message === "string" && e.message.trim()) return e.message;
  return "请求失败";
}
