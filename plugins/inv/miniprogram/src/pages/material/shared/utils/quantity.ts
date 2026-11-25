/** 领用数量展示：去除无意义的末尾零，保留十进制字符串的全部有效精度。 */
export function formatQuantity(value: string | number | null | undefined): string {
  if (value == null) return "—";
  const text = String(value).trim();
  const match = /^(-?\d+)(?:\.(\d*))?$/.exec(text);
  if (!match) return text;
  const whole = match[1]!.replace(/^(-?)0+(?=\d)/, "$1");
  const fraction = (match[2] || "").replace(/0+$/, "");
  if (!fraction) return whole === "-0" ? "0" : whole;
  return `${whole}.${fraction}`;
}
