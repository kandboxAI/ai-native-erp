import type { OptionsType } from "@/components/ReSegmented";

/** 菜单类型（字典 sys_menu_type） */
const menuTypeOptions: Array<OptionsType> = [
  { label: "目录", value: "directory" },
  { label: "菜单", value: "menu" },
  { label: "按钮", value: "button" }
];

/** 打开方式（字典 sys_open_target） */
const openTargetOptions: Array<OptionsType> = [
  { label: "当前页", value: "self" },
  { label: "新窗口", value: "blank" },
  { label: "内嵌", value: "iframe" }
];

const visibleOptions: Array<OptionsType> = [
  { label: "显示", tip: "会在菜单中显示", value: true },
  { label: "隐藏", tip: "不会在菜单中显示", value: false }
];

const activeOptions: Array<OptionsType> = [
  { label: "启用", value: true },
  { label: "停用", tip: "停用后不再下发给任何用户", value: false }
];

const menuTypeLabel = (code?: string | null) =>
  ({ directory: "目录", menu: "菜单", button: "按钮" })[code ?? ""] ??
  code ??
  "—";

export {
  menuTypeOptions,
  openTargetOptions,
  visibleOptions,
  activeOptions,
  menuTypeLabel
};
