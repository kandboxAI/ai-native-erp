<script setup lang="ts">
import { isAllEmpty } from "@pureadmin/utils";
import { useNav } from "@/layout/hooks/useNav";
import { transformI18n } from "@/plugins/i18n";
import LaySearch from "../lay-search/index.vue";
import DesktopModeSwitch from "../lay-navbar/DesktopModeSwitch.vue";
import { ref, watch, onMounted, nextTick } from "vue";
import { useRenderIcon } from "@/components/ReIcon/src/hooks";
import { getParentPaths, findRouteByPath } from "@/router/utils";
import { firstSidebarPath } from "@/router/sidebarLayout";
import { sidebarMenuIcon } from "./menuIcon";
import { useTranslationLang } from "../../hooks/useTranslationLang";
import { usePermissionStoreHook } from "@/store/modules/permission";
import LaySidebarExtraIcon from "../lay-sidebar/components/SidebarExtraIcon.vue";

import GlobalizationIcon from "@/assets/svg/globalization.svg?component";
import AccountSettingsIcon from "~icons/ri/user-settings-line";
import LogoutCircleRLine from "~icons/ri/logout-circle-r-line";
import Setting from "~icons/ri/settings-3-line";
import Check from "~icons/ep/check";

const menuRef = ref();
const defaultActive = ref(null);

const { t, route, locale, translationCh, translationEn } =
  useTranslationLang(menuRef);
const {
  device,
  logout,
  onPanel,
  username,
  userAvatar,
  getDivStyle,
  avatarsStyle,
  toAccountSettings,
  getDropdownItemStyle,
  getDropdownItemClass
} = useNav();

function getDefaultActive(routePath) {
  const menus = usePermissionStoreHook().sidebarMenus;
  const activePath = !isAllEmpty(route.meta?.activePath)
    ? route.meta.activePath
    : routePath;
  const rootPath = getParentPaths(activePath, menus)[0] || activePath;
  const root = findRouteByPath(rootPath, menus);
  defaultActive.value = root ? firstSidebarPath(root) : activePath;
}

onMounted(() => {
  getDefaultActive(route.path);
});

nextTick(() => {
  menuRef.value?.handleResize();
});

watch(
  () => [route.path, usePermissionStoreHook().sidebarMenus],
  () => {
    getDefaultActive(route.path);
  }
);
</script>

<template>
  <div
    v-if="device !== 'mobile'"
    v-loading="usePermissionStoreHook().sidebarMenus.length === 0"
    class="horizontal-header"
  >
    <el-menu
      ref="menuRef"
      router
      mode="horizontal"
      popper-class="pure-scrollbar"
      class="horizontal-header-menu"
      :default-active="defaultActive"
    >
      <el-menu-item
        v-for="route in usePermissionStoreHook().sidebarMenus"
        :key="route.path"
        :index="firstSidebarPath(route)"
      >
        <template #title>
          <div v-if="sidebarMenuIcon(route, 1)" class="sub-menu-icon">
            <component :is="useRenderIcon(sidebarMenuIcon(route, 1))" />
          </div>
          <div :style="getDivStyle">
            <span class="sidebar-menu-label select-none">
              {{ transformI18n(route.meta.title) }}
            </span>
            <LaySidebarExtraIcon :extraIcon="route.meta.extraIcon" />
          </div>
        </template>
      </el-menu-item>
    </el-menu>
    <div class="horizontal-header-right">
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
      <el-dropdown id="header-translation" trigger="click">
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
              <span v-show="locale === 'zh'" class="check-zh">
                <IconifyIconOffline :icon="Check" />
              </span>
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
      <el-dropdown trigger="click">
        <span class="el-dropdown-link navbar-bg-hover select-none">
          <img :src="userAvatar" :style="avatarsStyle" />
          <p v-if="username" class="dark:text-white">{{ username }}</p>
        </span>
        <template #dropdown>
          <el-dropdown-item @click="toAccountSettings">
            <IconifyIconOffline
              :icon="AccountSettingsIcon"
              style="margin: 5px"
            />
            {{ t("buttons.pureAccountSettings") }}
          </el-dropdown-item>
          <el-dropdown-menu class="logout">
            <el-dropdown-item @click="logout">
              <IconifyIconOffline
                :icon="LogoutCircleRLine"
                style="margin: 5px"
              />
              {{ t("buttons.pureLoginOut") }}
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>
  </div>
</template>

<style lang="scss" scoped>
:deep(.el-loading-mask) {
  opacity: 0.45;
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
