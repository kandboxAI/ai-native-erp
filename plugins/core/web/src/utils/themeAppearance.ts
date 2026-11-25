import {
  buttonPrimaryTokens,
  colorLuminance,
  normalizeHexColor
} from "./buttonTheme";

export function sidebarAppearanceTokens(
  background: unknown,
  primary: string
): Record<string, string> {
  const color = normalizeHexColor(background);
  if (!color) return {};
  const light = colorLuminance(color);
  const ink =
    (light + 0.05) / 0.05 > 1.05 / (light + 0.05) ? "#000000" : "#ffffff";
  return {
    "--app-sidebar-bg": color,
    "--app-sidebar-ink": ink,
    "--app-sidebar-hover": `color-mix(in srgb, ${ink} 8%, ${color})`,
    "--app-sidebar-active-bg":
      buttonPrimaryTokens(primary)["--app-button-primary-solid"],
    "--app-sidebar-active-ink": "#ffffff"
  };
}
