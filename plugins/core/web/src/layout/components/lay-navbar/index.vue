<script setup lang="ts">
import { computed } from "vue";
import { useRoute } from "vue-router";
import { useNav } from "@/layout/hooks/useNav";
import NavbarActions from "./NavbarActions.vue";
import LayNavMix from "../lay-sidebar/NavMix.vue";
import LaySidebarBreadCrumb from "../lay-sidebar/components/SidebarBreadCrumb.vue";
import LaySidebarTopCollapse from "../lay-sidebar/components/SidebarTopCollapse.vue";

const { layout, device, pureApp, toggleSideBar } = useNav();

// 隐藏侧边栏的首页类路由只保留右侧操作区，没有菜单可展开或定位。
const route = useRoute();
const routeHidesSidebar = computed(() => Boolean(route.meta.hideSidebar));
</script>

<template>
  <div class="navbar bg-white shadow-xs shadow-[rgba(0,21,41,0.08)]">
    <LaySidebarTopCollapse
      v-if="device === 'mobile' && !routeHidesSidebar"
      class="hamburger-container"
      :is-active="pureApp.sidebar.opened"
      @toggleClick="toggleSideBar"
    />

    <LaySidebarBreadCrumb
      v-if="layout !== 'mix' && device !== 'mobile' && !routeHidesSidebar"
      class="breadcrumb-container"
    />

    <LayNavMix v-if="layout === 'mix'" />

    <NavbarActions v-if="layout === 'vertical'" />
  </div>
</template>

<style lang="scss" scoped>
.navbar {
  width: 100%;
  height: 48px;
  overflow: hidden;

  .hamburger-container {
    float: left;
    height: 100%;
    line-height: 48px;
    cursor: pointer;
  }

  .breadcrumb-container {
    float: left;
    margin-left: 16px;
  }
}
</style>
