/** 数量只去掉无意义的末尾零，不经过浮点转换、不改变原有有效精度。 */
export function formatQuantity(
  value: string | number | null | undefined
): string {
  if (value == null || value === "") return "—";
  const text = String(value).trim();
  const match = /^([+-]?)(\d+)(?:\.(\d*))?(?:e([+-]?\d+))?$/i.exec(text);
  if (!match) return "—";
  const exponent = Number(match[4] || 0);
  if (!Number.isSafeInteger(exponent) || Math.abs(exponent) > 1000) return "—";
  const digits = match[2] + (match[3] || "");
  const position = match[2].length + exponent;
  const integer = (
    position <= 0 ? "0" : digits.slice(0, position).padEnd(position, "0")
  ).replace(/^0+(?=\d)/, "");
  const fraction = (
    position < 0 ? "0".repeat(-position) + digits : digits.slice(position)
  ).replace(/0+$/, "");
  const sign = match[1] === "-" && (integer !== "0" || fraction) ? "-" : "";
  return `${sign}${integer}${fraction ? `.${fraction}` : ""}`;
}
