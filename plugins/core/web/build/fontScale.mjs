/**
 * 统一缩放组件库、业务页面及 Tailwind 的显式字号，保留原有字号层次。
 * em、百分比和继承值已经随父级变化，不能再次缩放。
 * 不修改 rem 基准，避免同时放大宽高、间距和布局。
 */
export default function fontScale() {
  return {
    postcssPlugin: "app-font-scale",
    DeclarationExit(declaration) {
      if (declaration.prop !== "font-size") return;
      const value = declaration.value;
      if (
        value.includes("--app-font-scale") ||
        /(?:\d|\.)em\b|%|\b(?:inherit|initial|unset|revert|revert-layer)\b/i.test(
          value
        ) ||
        !/(?:\d|\.)(?:px|rem)\b|\bvar\(/i.test(value)
      )
        return;
      declaration.value = `calc((${value}) * var(--app-font-scale, 1))`;
    }
  };
}
