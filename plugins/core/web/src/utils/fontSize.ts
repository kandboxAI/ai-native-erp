export type FontSize = "default" | "large" | "extra-large";

const scales: Record<FontSize, number> = {
  default: 1,
  large: 16 / 14,
  "extra-large": 18 / 14
};

export function normalizeFontSize(value: unknown): FontSize {
  return value === "large" || value === "extra-large" ? value : "default";
}

/** 同时作用于页面及 teleport 到 body 的弹窗、下拉菜单。 */
export function applyFontSize(value: unknown): FontSize {
  const size = normalizeFontSize(value);
  document.documentElement.style.setProperty(
    "--app-font-scale",
    String(scales[size])
  );
  return size;
}
