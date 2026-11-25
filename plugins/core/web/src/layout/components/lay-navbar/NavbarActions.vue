<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { useNav } from "@/layout/hooks/useNav";
import LaySearch from "../lay-search/index.vue";
import { useTranslationLang } from "@/layout/hooks/useTranslationLang";
import DesktopModeSwitch from "./DesktopModeSwitch.vue";

import GlobalizationIcon from "@/assets/svg/globalization.svg?component";
import AccountSettingsIcon from "~icons/ri/user-settings-line";
import LogoutCircleRLine from "~icons/ri/logout-circle-r-line";
import Setting from "~icons/ri/settings-3-line";
import Check from "~icons/ep/check";

/** `compact` 用于标签栏内嵌，按钮高度与标签一致。 */
defineProps({
  compact: Boolean
});

const {
  logout,
  onPanel,
  username,
  userAvatar,
  avatarsStyle,
  toAccountSettings,
  getDropdownItemStyle,
  getDropdownItemClass
} = useNav();

const { t, locale, translationCh, translationEn } = useTranslationLang();

const userMenuVisible = ref(false);
const languageMenuVisible = ref(false);
const menuObscuresAssistant = computed(
  () => userMenuVisible.value || languageMenuVisible.value
);

// 原生助手不参与网页层叠，顶部菜单展开时复用静态预览让出显示区域。
watch(
  menuObscuresAssistant,
  obscured => {
    void window.erpDesktop?.setAssistantObscured(obscured);
  },
  { flush: "sync" }
);
onBeforeUnmount(() => {
  if (menuObscuresAssistant.value)
    void window.erpDesktop?.setAssistantObscured(false);
});
</script>

<template>
  <div :class="['navbar-actions', compact && 'navbar-actions--compact']">
    <!-- 菜单搜索 -->
    <LaySearch id="header-search" />
    <span
      class="set-icon navbar-bg-hover hover:[&>svg]:animate-scale-bounce"
      :title="t('buttons.pureOpenSystemSet')"
      @click="onPanel"
    >
      <IconifyIconOffline :icon="Setting" />
    </span>
    <!-- 国际化 -->
    <el-dropdown
      id="header-translation"
      trigger="click"
      @visible-change="languageMenuVisible = $event"
    >
      <div
        class="globalization-icon navbar-bg-hover hover:[&>svg]:animate-scale-bounce"
      >
        <IconifyIconOffline :icon="GlobalizationIcon" />
      </div>
      <template #dropdown>
        <el-dropdown-menu class="translation">
          <el-dropdown-item
            :style="getDropdownItemStyle(locale, 'zh')"
            :class="['dark:text-white!', getDropdownItemClass(locale, 'zh')]"
            @click="translationCh"
          >
            <IconifyIconOffline
              v-show="locale === 'zh'"
              class="check-zh"
              :icon="Check"
            />
            简体中文
          </el-dropdown-item>
          <el-dropdown-item
            :style="getDropdownItemStyle(locale, 'en')"
            :class="['dark:text-white!', getDropdownItemClass(locale, 'en')]"
            @click="translationEn"
          >
            <span v-show="locale === 'en'" class="check-en">
              <IconifyIconOffline :icon="Check" />
            </span>
            English
          </el-dropdown-item>
        </el-dropdown-menu>
      </template>
    </el-dropdown>
    <DesktopModeSwitch />
    <!-- 退出登录 -->
    <el-dropdown trigger="click" @visible-change="userMenuVisible = $event">
      <span class="el-dropdown-link navbar-bg-hover select-none">
        <img :src="userAvatar" :style="avatarsStyle" />
        <p v-if="username" class="dark:text-white">{{ username }}</p>
      </span>
      <template #dropdown>
        <el-dropdown-menu class="logout">
          <el-dropdown-item @click="toAccountSettings">
            <IconifyIconOffline
              :icon="AccountSettingsIcon"
              style="margin: 5px"
            />
            {{ t("buttons.pureAccountSettings") }}
          </el-dropdown-item>
          <el-dropdown-item @click="logout">
            <IconifyIconOffline :icon="LogoutCircleRLine" style="margin: 5px" />
            {{ t("buttons.pureLoginOut") }}
          </el-dropdown-item>
        </el-dropdown-menu>
      </template>
    </el-dropdown>
  </div>
</template>

<style lang="scss" scoped>
.navbar-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  height: 48px;
  color: #000000d9;

  .el-dropdown-link {
    display: flex;
    align-items: center;
    justify-content: space-around;
    height: 48px;
    padding: 10px;
    color: #000000d9;
    cursor: pointer;

    p {
      font-size: 14px;
    }

    img {
      width: 22px;
      height: 22px;
      border-radius: 50%;
    }
  }

  &--compact {
    flex: 0 0 auto;
    min-width: 0;
    height: 34px;
    padding-left: 8px;

    .el-dropdown-link {
      height: 34px;
      padding: 0 10px;
    }

    :deep(.globalization-icon),
    :deep(.fullscreen-icon),
    :deep(.dropdown-badge),
    :deep(.set-icon) {
      height: 34px;
    }

    :deep(.command-entry) {
      height: 28px;
    }
  }
}

.translation {
  :deep(.el-dropdown-menu__item) {
    padding: 5px 40px;
  }

  .check-zh {
    position: absolute;
    left: 20px;
  }

  .check-en {
    position: absolute;
    left: 20px;
  }
}

.logout {
  width: 120px;

  :deep(.el-dropdown-menu__item) {
    display: inline-flex;
    flex-wrap: wrap;
    min-width: 100%;
  }
}
</style>
