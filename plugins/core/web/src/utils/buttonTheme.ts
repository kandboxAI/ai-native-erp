export type ButtonAction =
  | "primary"
  | "view"
  | "import"
  | "export"
  | "edit"
  | "success"
  | "warning"
  | "danger"
  | "neutral";

/** Generic footers can declare an action; existing Element types remain a fallback. */
export function buttonActionFromType(type?: string): ButtonAction {
  return ["primary", "success", "warning", "danger"].includes(type ?? "")
    ? (type as ButtonAction)
    : "neutral";
}

/** Popconfirm accepts Element types; semantic actions remain the source of intent. */
export function buttonConfirmationType(action?: ButtonAction, type?: string) {
  const intent = action ?? buttonActionFromType(type);
  if (intent === "success" || intent === "export") return "success";
  if (intent === "warning" || intent === "danger") return intent;
  return "primary";
}

function luminance(rgb: number[]): number {
  return rgb.reduce((total, value, index) => {
    const channel = value / 255;
    const linear =
      channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
    return total + linear * [0.2126, 0.7152, 0.0722][index];
  }, 0);
}

function toHex(rgb: number[]): string {
  return `#${rgb.map(value => value.toString(16).padStart(2, "0")).join("")}`;
}

export function normalizeHexColor(value: unknown): string | undefined {
  if (typeof value !== "string") return;
  const hex = value.trim().replace(/^#/, "");
  if (!/^(?:[\da-f]{3}|[\da-f]{6})$/i.test(hex)) return;
  return `#${(hex.length === 3 ? [...hex].map(v => v + v).join("") : hex).toLowerCase()}`;
}

export function colorLuminance(color: string): number {
  const hex = normalizeHexColor(color);
  return hex
    ? luminance([1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16)))
    : 0;
}

function readableInk(rgb: number[], dark: boolean): string {
  const surface = dark ? [23, 25, 30] : [255, 255, 255];
  const soft = surface.map((v, i) => Math.round(v * 0.85 + rgb[i] * 0.15));
  const background = luminance(soft);
  for (let step = 0; step <= 20; step++) {
    const amount = step / 20;
    const candidate = rgb.map(v =>
      Math.round(v * (1 - amount) + (dark ? 255 : 0) * amount)
    );
    const ink = luminance(candidate);
    if (
      (Math.max(ink, background) + 0.05) / (Math.min(ink, background) + 0.05) >=
      4.5
    )
      return toHex(candidate);
  }
  return dark ? "#ffffff" : "#000000";
}

/** Button-only primary states; semantic colors and non-button components stay independent. */
export function buttonPrimaryTokens(
  color: string,
  textMode: "white" | "auto" = "white"
): Record<string, string> {
  const normalized = normalizeHexColor(color);
  if (!normalized) return {};
  const full = normalized.slice(1);
  const rgb = [0, 2, 4].map(index =>
    parseInt(full.slice(index, index + 2), 16)
  );
  const tokens: Record<string, string> = {};
  tokens["--app-button-primary-ink-light"] = readableInk(rgb, false);
  tokens["--app-button-primary-ink-dark"] = readableInk(rgb, true);
  let solid = rgb;
  if (textMode === "white") {
    for (let step = 0; step <= 100; step++) {
      solid = rgb.map(v => Math.round(v * (1 - step / 100)));
      if (1.05 / (luminance(solid) + 0.05) >= 4.5) break;
    }
  }
  for (const [state, amount] of [
    ["", 0],
    ["-hover", 0.1],
    ["-active", 0.18]
  ] as const) {
    const values = solid.map(value => Math.round(value * (1 - amount)));
    const background = toHex(values);
    const light = luminance(values);
    // White is the default; automatic contrast remains an explicit preference.
    const foreground =
      textMode === "auto" && (light + 0.05) / 0.05 > 1.05 / (light + 0.05)
        ? "#000000"
        : "#ffffff";
    tokens[`--app-button-primary${state}-solid`] = background;
    tokens[`--app-button-primary${state}-contrast`] = foreground;
  }
  return tokens;
}
