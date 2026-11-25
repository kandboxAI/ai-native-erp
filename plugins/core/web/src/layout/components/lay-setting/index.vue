<script setup lang="ts">
import {
  ref,
  unref,
  watch,
  reactive,
  computed,
  nextTick,
  onUnmounted,
  onBeforeMount
} from "vue";
import { useI18n } from "vue-i18n";
import { emitter } from "@/utils/mitt";
import { applyFontSize, normalizeFontSize } from "@/utils/fontSize";
import LayPanel from "../lay-panel/index.vue";
import { useNav } from "@/layout/hooks/useNav";
import { useAppStoreHook } from "@/store/modules/app";
import { useMultiTagsStoreHook } from "@/store/modules/multiTags";
import Segmented, { type OptionsType } from "@/components/ReSegmented";
import { useDataThemeChange } from "@/layout/hooks/useDataThemeChange";
import { useDark, useGlobal, debounce, isNumber } from "@pureadmin/utils";

import Check from "~icons/ep/check";
import LeftArrow from "~icons/ri/arrow-left-s-line?width=20&height=20";
import RightArrow from "~icons/ri/arrow-right-s-line?width=20&height=20";
import DayIcon from "@/assets/svg/day.svg?component";
import DarkIcon from "@/assets/svg/dark.svg?component";
import SystemIcon from "@/assets/svg/system.svg?component";

const { t } = useI18n();
const { device } = useNav();
const { isDark } = useDark();
const { $storage } = useGlobal<GlobalPropertiesApi>();

const mixRef = ref();
const verticalRef = ref();
const horizontalRef = ref();

const {
  dataTheme,
  themeMode,
  layoutTheme,
  themeColors,
  primaryColor,
  sidebarColor,
  primaryButtonText,
  setCustomThemeColor,
  resetThemeColor,
  setPrimaryButtonText,
  setSidebarBackground,
  toggleClass,
  dataThemeChange,
  setLayoutThemeColor
} = useDataThemeChange();

const primaryColorDraft = ref("");
const sidebarColorDraft = ref("");
const primaryColorError = ref("");
const sidebarColorError = ref("");
watch(
  [primaryColor, () => layoutTheme.value.themeColor],
  ([value]) => {
    primaryColorDraft.value = value;
    primaryColorError.value = "";
  },
  { immediate: true }
);
watch(
  [sidebarColor, dataTheme],
  ([value]) => {
    sidebarColorDraft.value = value;
    sidebarColorError.value = "";
  },
  { immediate: true }
);

function applyPrimaryColor(value: unknown) {
  if (value === null) return restorePrimaryColor();
  primaryColorError.value = setCustomThemeColor(value)
    ? ""
    : "请输入有效色值，例如 #722ED1";
  if (!primaryColorError.value) primaryColorDraft.value = primaryColor.value;
}

function applySidebarColor(value: unknown) {
  sidebarColorError.value = setSidebarBackground(value)
    ? ""
    : "请输入有效色值，例如 #FFFFFF";
  if (!sidebarColorError.value) sidebarColorDraft.value = sidebarColor.value;
}

function restorePrimaryColor() {
  resetThemeColor();
  primaryColorDraft.value = primaryColor.value;
  primaryColorError.value = "";
}

function restoreSidebarColor() {
  setSidebarBackground(null);
  sidebarColorDraft.value = sidebarColor.value;
  sidebarColorError.value = "";
}

function changeButtonText(value: string | number | boolean | undefined) {
  setPrimaryButtonText(value === "auto" ? "auto" : "white");
}

/* body添加layout属性，作用于src/style/sidebar.scss */
if (unref(layoutTheme)) {
  const layout = unref(layoutTheme).layout;
  const theme = unref(layoutTheme).theme;
  document.documentElement.setAttribute("data-theme", theme);
  setMenuLayout(layout);
}

/** 页签风格默认为谷歌风格 */
const tagsStyleValue = ref($storage.configure?.tagsStyle ?? "chrome");

const logoVal = ref($storage.configure?.showLogo ?? true);

const watermarkConfigs = reactive({
  enable: $storage.configure.watermark,
  text: $storage.configure.watermarkText
});

const settings = reactive({
  greyVal: $storage.configure.grey,
  weakVal: $storage.configure.weak,
  tabsVal: $storage.configure.hideTabs,
  showLogo: $storage.configure.showLogo,
  tagsStyle: $storage.configure.tagsStyle,
  hideFooter: $storage.configure.hideFooter,
  multiTagsCache: $storage.configure.multiTagsCache,
  stretch: $storage.configure.stretch
});

const getThemeColorStyle = computed(() => {
  return color => {
    return { background: color };
  };
});

/** 当网页整体为暗色风格时不显示亮白色主题配色切换选项 */
const showThemeColors = computed(() => {
  return themeColor => {
    return themeColor === "light" && isDark.value ? false : true;
  };
});

function storageConfigureChange<T>(key: string, val: T): void {
  const storageConfigure = $storage.configure;
  storageConfigure[key] = val;
  $storage.configure = storageConfigure;
}

const fontSize = computed(() =>
  normalizeFontSize($storage.configure?.fontSize)
);

function changeFontSize(value: string | number | boolean | undefined) {
  storageConfigureChange("fontSize", applyFontSize(value));
}

/** 灰色模式设置 */
const greyChange = (value): void => {
  const htmlEl = document.querySelector("html");
  toggleClass(settings.greyVal, "html-grey", htmlEl);
  storageConfigureChange("grey", value);
};

/** 色弱模式设置 */
const weekChange = (value): void => {
  const htmlEl = document.querySelector("html");
  toggleClass(settings.weakVal, "html-weakness", htmlEl);
  storageConfigureChange("weak", value);
};

/** 隐藏标签页设置 */
const tagsChange = () => {
  const showVal = settings.tabsVal;
  storageConfigureChange("hideTabs", showVal);
  emitter.emit("tagViewsChange", showVal as unknown as string);
};

/** 隐藏页脚设置 */
const hideFooterChange = () => {
  const hideFooter = settings.hideFooter;
  storageConfigureChange("hideFooter", hideFooter);
};

/** 标签页持久化设置 */
const multiTagsCacheChange = () => {
  const multiTagsCache = settings.multiTagsCache;
  storageConfigureChange("multiTagsCache", multiTagsCache);
  useMultiTagsStoreHook().multiTagsCacheChange(multiTagsCache);
};

function onChange({ option }) {
  const { value } = option;
  tagsStyleValue.value = value;
  storageConfigureChange("tagsStyle", value);
  emitter.emit("tagViewsTagsStyle", value);
}

function onWatermarkSwitchChange(value) {
  storageConfigureChange("watermark", value);
}

function onWatermarkInputChange(text) {
  storageConfigureChange("watermarkText", text);
}

/** 侧边栏Logo */
function logoChange() {
  unref(logoVal)
    ? storageConfigureChange("showLogo", true)
    : storageConfigureChange("showLogo", false);
  emitter.emit("logoChange", unref(logoVal));
}

function setFalse(Doms): any {
  Doms.forEach(v => {
    toggleClass(false, "is-select", unref(v));
  });
}

/** 页宽 */
const stretchTypeOptions = computed<Array<OptionsType>>(() => {
  return [
    {
      label: t("panel.pureStretchFixed"),
      tip: t("panel.pureStretchFixedTip"),
      value: "fixed"
    },
    {
      label: t("panel.pureStretchCustom"),
      tip: t("panel.pureStretchCustomTip"),
      value: "custom"
    }
  ];
});

const setStretch = value => {
  settings.stretch = value;
  storageConfigureChange("stretch", value);
};

const stretchTypeChange = ({ option }) => {
  const { value } = option;
  value === "custom" ? setStretch(1440) : setStretch(false);
};

/** 主题色 激活选择项 */
const getThemeColor = computed(() => {
  return current => {
    if (
      current === layoutTheme.value.theme &&
      layoutTheme.value.theme !== "light"
    ) {
      return "#fff";
    } else if (
      current === layoutTheme.value.theme &&
      layoutTheme.value.theme === "light"
    ) {
      return "#1d2b45";
    } else {
      return "transparent";
    }
  };
});

const pClass = computed(() => {
  return ["mb-3!", "font-medium", "text-sm", "dark:text-white"];
});

const themeOptions = computed<Array<OptionsType>>(() => {
  return [
    {
      label: t("panel.pureThemeModeLight"),
      icon: DayIcon,
      theme: "light",
      tip: t("panel.pureThemeModeLightTip"),
      iconAttrs: { fill: isDark.value ? "#fff" : "#000" }
    },
    {
      label: t("panel.pureThemeModeDark"),
      icon: DarkIcon,
      theme: "dark",
      tip: t("panel.pureThemeModeDarkTip"),
      iconAttrs: { fill: isDark.value ? "#fff" : "#000" }
    },
    {
      label: t("panel.pureThemeModeSystem"),
      icon: SystemIcon,
      theme: "system",
      tip: t("panel.pureThemeModeSystemTip"),
      iconAttrs: { fill: isDark.value ? "#fff" : "#000" }
    }
  ];
});

const markOptions = computed<Array<OptionsType>>(() => {
  return [
    {
      label: t("panel.pureTagsStyleSmart"),
      tip: t("panel.pureTagsStyleSmartTip"),
      value: "smart"
    },
    {
      label: t("panel.pureTagsStyleCard"),
      tip: t("panel.pureTagsStyleCardTip"),
      value: "card"
    },
    {
      label: t("panel.pureTagsStyleChrome"),
      tip: t("panel.pureTagsStyleChromeTip"),
      value: "chrome"
    }
  ];
});

/** 设置菜单布局 */
function setMenuLayout(layout: string) {
  layoutTheme.value.layout = layout;
  window.document.body.setAttribute("layout", layout);
  $storage.layout = {
    ...$storage.layout,
    layout,
    theme: layoutTheme.value.theme,
    darkMode: $storage.layout?.darkMode,
    sidebarStatus: $storage.layout?.sidebarStatus,
    epThemeColor: $storage.layout?.epThemeColor,
    themeColor: $storage.layout?.themeColor,
    themeMode: $storage.layout?.themeMode
  };
  useAppStoreHook().setLayout(layout);
}

watch($storage, ({ layout }) => {
  switch (layout["layout"]) {
    case "vertical":
      toggleClass(true, "is-select", unref(verticalRef));
      debounce(setFalse([horizontalRef]), 50);
      debounce(setFalse([mixRef]), 50);
      break;
    case "horizontal":
      toggleClass(true, "is-select", unref(horizontalRef));
      debounce(setFalse([verticalRef]), 50);
      debounce(setFalse([mixRef]), 50);
      break;
    case "mix":
      toggleClass(true, "is-select", unref(mixRef));
      debounce(setFalse([verticalRef]), 50);
      debounce(setFalse([horizontalRef]), 50);
      break;
  }
});

const mediaQueryList = window.matchMedia("(prefers-color-scheme: dark)");

/** 根据操作系统主题设置平台主题模式 */
function updateTheme() {
  if (themeMode.value !== "system") return;
  if (mediaQueryList.matches) {
    dataTheme.value = true;
  } else {
    dataTheme.value = false;
  }
  dataThemeChange(themeMode.value);
}

function removeMatchMedia() {
  mediaQueryList.removeEventListener("change", updateTheme);
}

/** 监听操作系统主题改变 */
function watchSystemThemeChange() {
  updateTheme();
  removeMatchMedia();
  mediaQueryList.addEventListener("change", updateTheme);
}

onBeforeMount(() => {
  /* 初始化系统配置 */
  nextTick(() => {
    watchSystemThemeChange();
    settings.greyVal &&
      document.querySelector("html")?.classList.add("html-grey");
    settings.weakVal &&
      document.querySelector("html")?.classList.add("html-weakness");
    settings.tabsVal && tagsChange();
    settings.hideFooter && hideFooterChange();
  });
});

onUnmounted(removeMatchMedia);
</script>

<template>
  <LayPanel>
    <div class="p-5">
      <div class="appearance-setting font-size-setting">
        <p class="appearance-label">文字大小</p>
        <el-radio-group
          :model-value="fontSize"
          aria-label="文字大小"
          @change="changeFontSize"
        >
          <el-radio-button value="default">标准</el-radio-button>
          <el-radio-button value="large">较大</el-radio-button>
          <el-radio-button value="extra-large">特大</el-radio-button>
        </el-radio-group>
        <p class="font-size-preview">文字大小预览</p>
        <p class="appearance-hint">
          即时生效，适用于菜单、表格、表单等系统文字；设置保存在当前浏览器。
        </p>
      </div>
      <p :class="pClass">{{ t("panel.pureThemeMode") }}</p>
      <Segmented
        resize
        class="select-none"
        :modelValue="themeMode === 'system' ? 2 : dataTheme ? 1 : 0"
        :options="themeOptions"
        @change="
          theme => {
            theme.index === 1 && theme.index !== 2
              ? (dataTheme = true)
              : (dataTheme = false);
            themeMode = theme.option.theme;
            dataThemeChange(theme.option.theme);
            theme.index === 2 && watchSystemThemeChange();
          }
        "
      />

      <p :class="['mt-5!', pClass]">{{ t("panel.pureThemeColor") }}</p>
      <ul class="theme-color">
        <li
          v-for="(item, index) in themeColors"
          v-show="showThemeColors(item.themeColor)"
          :key="index"
          :style="getThemeColorStyle(item.color)"
          @click="setLayoutThemeColor(item.themeColor)"
        >
          <el-icon
            class="mt-px"
            :size="20"
            :color="getThemeColor(item.themeColor)"
          >
            <IconifyIconOffline :icon="Check" />
          </el-icon>
        </li>
      </ul>

      <div class="appearance-setting">
        <label for="appearance-primary-color">自定义主题色</label>
        <div class="appearance-color-row">
          <el-color-picker
            :model-value="primaryColor"
            popper-class="settings-color-popper"
            color-format="hex"
            aria-label="选择主题色"
            @change="applyPrimaryColor"
          />
          <el-input
            id="appearance-primary-color"
            v-model="primaryColorDraft"
            aria-label="主题色色值"
            placeholder="#722ED1"
            @change="applyPrimaryColor"
            @keyup.enter="applyPrimaryColor(primaryColorDraft)"
          />
          <el-button
            data-action="neutral"
            link
            aria-label="恢复默认主题色"
            @click="restorePrimaryColor"
            >恢复默认</el-button
          >
        </div>
        <p v-if="primaryColorError" class="appearance-error" role="alert">
          {{ primaryColorError }}
        </p>
      </div>

      <div class="appearance-setting">
        <p class="appearance-label">主按钮文字</p>
        <el-radio-group
          :model-value="primaryButtonText"
          aria-label="主按钮文字"
          @change="changeButtonText"
        >
          <el-radio-button value="white">统一白字</el-radio-button>
          <el-radio-button value="auto">自动对比</el-radio-button>
        </el-radio-group>
        <p class="appearance-hint">
          白字模式会适当加深较亮的按钮底色，保持文字清晰。
        </p>
      </div>

      <div class="appearance-setting">
        <label for="appearance-sidebar-color"
          >导航底色（{{ dataTheme ? "深色模式" : "浅色模式" }}）</label
        >
        <div class="appearance-color-row">
          <el-color-picker
            :model-value="sidebarColor"
            popper-class="settings-color-popper"
            color-format="hex"
            aria-label="选择导航底色"
            @change="applySidebarColor"
          />
          <el-input
            id="appearance-sidebar-color"
            v-model="sidebarColorDraft"
            aria-label="导航底色色值"
            placeholder="#FFFFFF"
            @change="applySidebarColor"
            @keyup.enter="applySidebarColor(sidebarColorDraft)"
          />
          <el-button
            data-action="neutral"
            link
            aria-label="恢复默认导航底色"
            @click="restoreSidebarColor"
            >恢复默认</el-button
          >
        </div>
        <p v-if="sidebarColorError" class="appearance-error" role="alert">
          {{ sidebarColorError }}
        </p>
        <p class="appearance-hint">
          浅色、深色模式分别保存；菜单文字自动适配底色。设置保存在当前浏览器。
        </p>
      </div>

      <p :class="['mt-5!', pClass]">{{ t("panel.pureMenuLayout") }}</p>
      <ul class="pure-theme">
        <li
          ref="verticalRef"
          v-tippy="{
            content: t('panel.pureVerticalTip'),
            zIndex: 41000
          }"
          :class="layoutTheme.layout === 'vertical' ? 'is-select' : ''"
          @click="setMenuLayout('vertical')"
        >
          <div />
          <div />
        </li>
        <li
          v-if="device !== 'mobile'"
          ref="horizontalRef"
          v-tippy="{
            content: t('panel.pureHorizontalTip'),
            zIndex: 41000
          }"
          :class="layoutTheme.layout === 'horizontal' ? 'is-select' : ''"
          @click="setMenuLayout('horizontal')"
        >
          <div />
          <div />
        </li>
        <li
          v-if="device !== 'mobile'"
          ref="mixRef"
          v-tippy="{
            content: t('panel.pureMixTip'),
            zIndex: 41000
          }"
          :class="layoutTheme.layout === 'mix' ? 'is-select' : ''"
          @click="setMenuLayout('mix')"
        >
          <div />
          <div />
        </li>
      </ul>

      <span v-if="useAppStoreHook().getViewportWidth > 1280">
        <p :class="['mt-5!', pClass]">{{ t("panel.pureStretch") }}</p>
        <Segmented
          resize
          class="mb-2 select-none"
          :modelValue="isNumber(settings.stretch) ? 1 : 0"
          :options="stretchTypeOptions"
          @change="stretchTypeChange"
        />
        <el-input-number
          v-if="isNumber(settings.stretch)"
          v-model="settings.stretch as number"
          :min="1280"
          :max="1600"
          controls-position="right"
          @change="value => setStretch(value)"
        />
        <button
          v-else
          v-ripple="{ class: 'text-gray-300' }"
          class="bg-transparent flex-c w-full h-20 rounded-md border border-(--pure-border-color)"
          @click="setStretch(!settings.stretch)"
        >
          <div
            class="flex-bc transition-all duration-300"
            :class="[settings.stretch ? 'w-[24%]' : 'w-[50%]']"
            style="color: var(--el-color-primary)"
          >
            <IconifyIconOffline
              :icon="settings.stretch ? RightArrow : LeftArrow"
            />
            <div
              class="grow border-0 border-b border-dashed"
              style="border-color: var(--el-color-primary)"
            />
            <IconifyIconOffline
              :icon="settings.stretch ? LeftArrow : RightArrow"
            />
          </div>
        </button>
      </span>

      <p :class="['mt-5!', pClass]">{{ t("panel.pureTagsStyle") }}</p>
      <Segmented
        resize
        class="select-none"
        :modelValue="
          tagsStyleValue === 'smart' ? 0 : tagsStyleValue === 'card' ? 1 : 2
        "
        :options="markOptions"
        @change="onChange"
      />

      <p class="mt-5! font-medium text-sm dark:text-white">
        {{ t("panel.pureFullScreenWatermark") }}
      </p>
      <ul class="setting">
        <li>
          <span class="dark:text-white">
            {{ t("panel.pureEnableWatermark") }}
          </span>
          <el-switch
            v-model="watermarkConfigs.enable"
            inline-prompt
            :active-text="t('buttons.pureOpenText')"
            :inactive-text="t('buttons.pureCloseText')"
            @change="onWatermarkSwitchChange"
          />
        </li>
        <li v-if="watermarkConfigs.enable" v-motion-fade>
          <span class="dark:text-white">
            {{ t("panel.pureWatermarkText") }}
          </span>
          <el-input
            v-model="watermarkConfigs.text"
            class="w-32!"
            clearable
            :placeholder="t('panel.pureWatermarkTextPlaceholder')"
            @input="onWatermarkInputChange"
          />
        </li>
      </ul>

      <p class="mt-3! font-medium text-sm dark:text-white">
        {{ t("panel.pureInterfaceDisplay") }}
      </p>
      <ul class="setting">
        <li>
          <span class="dark:text-white">{{ t("panel.pureHiddenTags") }}</span>
          <el-switch
            v-model="settings.tabsVal"
            inline-prompt
            :active-text="t('buttons.pureOpenText')"
            :inactive-text="t('buttons.pureCloseText')"
            @change="tagsChange"
          />
        </li>
        <li>
          <span class="dark:text-white">{{ t("panel.pureHiddenFooter") }}</span>
          <el-switch
            v-model="settings.hideFooter"
            inline-prompt
            :active-text="t('buttons.pureOpenText')"
            :inactive-text="t('buttons.pureCloseText')"
            @change="hideFooterChange"
          />
        </li>
        <li>
          <span class="dark:text-white">
            {{ t("panel.pureMultiTagsCache") }}
          </span>
          <el-switch
            v-model="settings.multiTagsCache"
            inline-prompt
            :active-text="t('buttons.pureOpenText')"
            :inactive-text="t('buttons.pureCloseText')"
            @change="multiTagsCacheChange"
          />
        </li>
        <li>
          <span class="dark:text-white">Logo</span>
          <el-switch
            v-model="logoVal"
            inline-prompt
            :active-value="true"
            :inactive-value="false"
            :active-text="t('buttons.pureOpenText')"
            :inactive-text="t('buttons.pureCloseText')"
            @change="logoChange"
          />
        </li>
        <li>
          <span class="dark:text-white">{{ t("panel.pureGreyModel") }}</span>
          <el-switch
            v-model="settings.greyVal"
            inline-prompt
            :active-text="t('buttons.pureOpenText')"
            :inactive-text="t('buttons.pureCloseText')"
            @change="greyChange"
          />
        </li>
        <li>
          <span class="dark:text-white">{{ t("panel.pureWeakModel") }}</span>
          <el-switch
            v-model="settings.weakVal"
            inline-prompt
            :active-text="t('buttons.pureOpenText')"
            :inactive-text="t('buttons.pureCloseText')"
            @change="weekChange"
          />
        </li>
      </ul>
    </div>
  </LayPanel>
</template>

<style lang="scss" scoped>
:deep(.el-divider__text) {
  font-size: 16px;
  font-weight: 700;
}

:deep(.el-switch__core) {
  --el-switch-off-color: var(--pure-switch-off-color);

  min-width: 36px;
  height: 18px;
}

:deep(.el-switch__core .el-switch__action) {
  height: 14px;
}

.theme-color {
  display: flex;
  gap: 8px;
  margin-top: 8px;

  li {
    position: relative;
    width: 21px;
    height: 21px;
    cursor: pointer;
    border-radius: 4px;
    box-shadow: rgb(0 0 0 / 15%) 0 0 0 1px inset;
    transition: all 0.2s ease;

    &:hover {
      box-shadow:
        rgb(0 0 0 / 25%) 0 0 0 1px inset,
        0 2px 4px rgb(0 0 0 / 15%);
      transform: scale(1.1);
    }
  }
}

.pure-theme {
  display: flex;
  gap: 12px;

  li {
    position: relative;
    width: 46px;
    height: 36px;
    overflow: hidden;
    cursor: pointer;
    background: #f0f2f5;
    border-radius: 4px;
    box-shadow: 0 1px 2.5px 0 rgb(0 0 0 / 18%);

    &:nth-child(1) {
      div {
        &:nth-child(1) {
          width: 30%;
          height: 100%;
          background: #1b2a47;
        }

        &:nth-child(2) {
          position: absolute;
          top: 0;
          right: 0;
          width: 70%;
          height: 30%;
          background: #fff;
          box-shadow: 0 0 1px #888;
        }
      }
    }

    &:nth-child(2) {
      div {
        &:nth-child(1) {
          width: 100%;
          height: 30%;
          background: #1b2a47;
          box-shadow: 0 0 1px #888;
        }
      }
    }

    &:nth-child(3) {
      div {
        &:nth-child(1) {
          width: 100%;
          height: 30%;
          background: #1b2a47;
          box-shadow: 0 0 1px #888;
        }

        &:nth-child(2) {
          position: absolute;
          bottom: 0;
          left: 0;
          width: 30%;
          height: 70%;
          background: #fff;
          box-shadow: 0 0 1px #888;
        }
      }
    }
  }
}

.is-select {
  border: 2px solid var(--el-color-primary);
}

.setting {
  li {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 3px 0;
    font-size: 14px;
  }
}

.appearance-setting {
  margin-top: 16px;

  > label,
  > .appearance-label {
    display: block;
    margin: 0 0 8px;
    font-size: 14px;
    color: var(--el-text-color-primary);
  }
}

.font-size-setting {
  margin-top: 0;
  margin-bottom: 20px;
}

.font-size-preview {
  margin: 12px 0 0;
  font-size: 14px;
  line-height: 1.6;
  color: var(--el-text-color-primary);
}

.appearance-color-row {
  display: flex;
  align-items: center;
  gap: 8px;

  .el-input {
    flex: 1;
    min-width: 0;
  }
  .el-button {
    margin-left: 0;
    font-size: 12px;
  }
}

.appearance-hint,
.appearance-error {
  margin: 8px 0 0;
  font-size: 12px;
  line-height: 1.6;
  color: var(--el-text-color-secondary);
}
.appearance-error {
  color: var(--el-color-danger);
}

// ColorPicker teleports to body; keep it above the settings panel (40000).
:global(.el-popper.settings-color-popper) {
  z-index: 41010 !important;
}
</style>
