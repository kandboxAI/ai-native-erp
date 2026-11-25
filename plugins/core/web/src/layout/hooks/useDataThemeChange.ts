import { ref, computed } from "vue";
import { getConfig } from "@/config";
import { applyFontSize } from "@/utils/fontSize";
import { useLayout } from "./useLayout";
import { removeToken } from "@/utils/auth";
import { routerArrays } from "@/layout/types";
import { router, resetRouter } from "@/router";
import type { themeColorsType } from "../types";
import { useAppStoreHook } from "@/store/modules/app";
import { useEpThemeStoreHook } from "@/store/modules/epTheme";
import { useMultiTagsStoreHook } from "@/store/modules/multiTags";
import { darken, lighten, useGlobal, storageLocal } from "@pureadmin/utils";
import { buttonPrimaryTokens, normalizeHexColor } from "@/utils/buttonTheme";
import { sidebarAppearanceTokens } from "@/utils/themeAppearance";

export function useDataThemeChange() {
  const { layoutTheme, layout } = useLayout();
  const themeColors = ref<Array<themeColorsType>>([
    /* 亮白色 */
    { color: "#ffffff", themeColor: "light" },
    /* 道奇蓝 */
    { color: "#1b2a47", themeColor: "default" },
    /* 深紫罗兰色 */
    { color: "#722ed1", themeColor: "saucePurple" },
    /* 深粉色 */
    { color: "#eb2f96", themeColor: "pink" },
    /* 猩红色 */
    { color: "#f5222d", themeColor: "dusk" },
    /* 橙红色 */
    { color: "#fa541c", themeColor: "volcano" },
    /* 绿宝石 */
    { color: "#13c2c2", themeColor: "mingQing" },
    /* 酸橙绿 */
    { color: "#52c41a", themeColor: "auroraGreen" }
  ]);

  const { $storage } = useGlobal<GlobalPropertiesApi>();
  const dataTheme = ref<boolean>($storage?.layout?.darkMode);
  const themeMode = ref<string>($storage?.layout?.themeMode);
  const body = document.documentElement as HTMLElement;

  function toggleClass(flag: boolean, clsName: string, target?: HTMLElement) {
    const targetEl = target || document.body;
    let { className } = targetEl;
    className = className.replace(clsName, "").trim();
    targetEl.className = flag ? `${className} ${clsName}` : className;
  }

  /** 设置导航主题色 */
  function setLayoutThemeColor(
    theme = getConfig().Theme ?? "light",
    isClick = true
  ) {
    const selected = isClick ? theme : $storage.layout.themeColor || theme;
    const effective =
      selected === "light" && dataTheme.value ? "default" : selected;
    document.documentElement.setAttribute("data-theme", effective);
    $storage.layout = {
      ...$storage.layout,
      layout: layout.value,
      theme: effective,
      darkMode: dataTheme.value,
      themeColor: selected,
      themeMode: themeMode.value
    };
    const primary =
      effective === "custom"
        ? normalizeHexColor($storage.layout.customThemeColor)
        : effective === "default" || effective === "light"
          ? getConfig().EpThemeColor
          : themeColors.value.find(v => v.themeColor === effective)?.color;
    setEpThemeColor(primary || getConfig().EpThemeColor || "#2468a8");
  }

  function applySidebarBackground() {
    const background = dataTheme.value
      ? $storage.layout.sidebarDarkColor
      : $storage.layout.sidebarLightColor;
    const tokens = sidebarAppearanceTokens(
      background,
      useEpThemeStoreHook().epThemeColor
    );
    if (Object.keys(tokens).length) {
      body.setAttribute("data-sidebar-custom", "");
      for (const [name, value] of Object.entries(tokens))
        body.style.setProperty(name, value);
    } else {
      body.removeAttribute("data-sidebar-custom");
      for (const name of ["bg", "ink", "hover", "active-bg", "active-ink"])
        body.style.removeProperty(`--app-sidebar-${name}`);
    }
  }

  const primaryColor = computed(
    () =>
      normalizeHexColor(layoutTheme.value.epThemeColor) ||
      getConfig().EpThemeColor ||
      "#2468a8"
  );
  const primaryButtonText = computed(() =>
    layoutTheme.value.primaryButtonText === "auto" ? "auto" : "white"
  );
  const sidebarColor = computed(() => {
    const settings = layoutTheme.value;
    // Include the preset in the dependency list before reading its CSS default.
    void settings.theme;
    return (
      normalizeHexColor(
        dataTheme.value ? settings.sidebarDarkColor : settings.sidebarLightColor
      ) ||
      (dataTheme.value
        ? "#141414"
        : normalizeHexColor(
            getComputedStyle(body).getPropertyValue("--pure-theme-menu-bg")
          ) || "#ffffff")
    );
  });

  function setCustomThemeColor(value: unknown) {
    const color = normalizeHexColor(value);
    if (!color) return false;
    $storage.layout = { ...$storage.layout, customThemeColor: color };
    setLayoutThemeColor("custom");
    return true;
  }

  function resetThemeColor() {
    $storage.layout = { ...$storage.layout, customThemeColor: undefined };
    setLayoutThemeColor(getConfig().Theme || "light");
  }

  function setPrimaryButtonText(value: "white" | "auto") {
    $storage.layout = {
      ...$storage.layout,
      primaryButtonText: value === "auto" ? "auto" : "white"
    };
    setEpThemeColor(primaryColor.value);
  }

  function setSidebarBackground(value: unknown) {
    const color = value == null ? undefined : normalizeHexColor(value);
    if (value != null && !color) return false;
    const key = dataTheme.value ? "sidebarDarkColor" : "sidebarLightColor";
    $storage.layout = { ...$storage.layout, [key]: color };
    applySidebarBackground();
    return true;
  }

  function setPropertyPrimary(mode: string, i: number, color: string) {
    document.documentElement.style.setProperty(
      `--el-color-primary-${mode}-${i}`,
      dataTheme.value ? darken(color, i / 10) : lighten(color, i / 10)
    );
  }

  /** 设置 `element-plus` 主题色 */
  const setEpThemeColor = (value: string) => {
    const color = normalizeHexColor(value);
    if (!color) return;
    useEpThemeStoreHook().setEpThemeColor(color);
    document.documentElement.style.setProperty("--el-color-primary", color);
    body.style.setProperty(
      "--app-navigation-active-bg",
      buttonPrimaryTokens(color)["--app-button-primary-solid"]
    );
    for (const [name, value] of Object.entries(
      buttonPrimaryTokens(color, primaryButtonText.value)
    )) {
      document.documentElement.style.setProperty(name, value);
    }
    for (let i = 1; i <= 2; i++) {
      setPropertyPrimary("dark", i, color);
    }
    for (let i = 1; i <= 9; i++) {
      setPropertyPrimary("light", i, color);
    }
    applySidebarBackground();
  };

  /** 浅色、深色主题模式切换 */
  function dataThemeChange(mode?: string) {
    themeMode.value = mode;
    body.classList.toggle("dark", dataTheme.value);
    setLayoutThemeColor(
      $storage.layout.themeColor ||
        $storage.layout.theme ||
        getConfig().Theme ||
        "light",
      false
    );
  }

  /** 清空缓存并返回登录页 */
  function onReset() {
    $storage.configure = {
      ...$storage.configure,
      fontSize: applyFontSize("default")
    };
    removeToken();
    storageLocal().clear();
    const { Grey, Weak, MultiTagsCache, EpThemeColor, Layout } = getConfig();
    useAppStoreHook().setLayout(Layout);
    setEpThemeColor(EpThemeColor);
    useMultiTagsStoreHook().multiTagsCacheChange(MultiTagsCache);
    toggleClass(Grey, "html-grey", document.querySelector("html"));
    toggleClass(Weak, "html-weakness", document.querySelector("html"));
    router.push("/login");
    useMultiTagsStoreHook().handleTags("equal", [...routerArrays]);
    resetRouter();
  }

  return {
    body,
    primaryColor,
    sidebarColor,
    primaryButtonText,
    setCustomThemeColor,
    resetThemeColor,
    setPrimaryButtonText,
    setSidebarBackground,
    dataTheme,
    themeMode,
    layoutTheme,
    themeColors,
    onReset,
    toggleClass,
    dataThemeChange,
    setEpThemeColor,
    setLayoutThemeColor
  };
}
