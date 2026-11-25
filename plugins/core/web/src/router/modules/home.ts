import { $t } from "@/plugins/i18n";
import { home } from "@/router/enums";
const { VITE_HIDE_HOME } = import.meta.env;
const Layout = () => import("@/layout/index.vue");

export default {
  path: "/",
  name: "Home",
  component: Layout,
  redirect: "/workbench",
  meta: {
    icon: "ri:home-4-line",
    title: $t("menus.pureHome"),
    showLink: false,
    rank: home
  },
  children: [
    {
      path: "/assistant",
      name: "DesktopAssistant",
      props: () => (window.erpDesktop ? { surface: "assistant" } : {}),
      component: () => import("@/views/workbench/index.vue"),
      beforeEnter: () => (window.erpDesktop ? true : "/workbench"),
      meta: {
        title: "智能体",
        hiddenTag: true,
        icon: "ri:sparkling-line",
        hideSidebar: true,
        showLink: false
      }
    },
    {
      path: "/workbench",
      name: "PlatformWorkbench",
      component: () => import("@/views/application-center/index.vue"),
      meta: {
        title: "工作台",
        icon: "ri:dashboard-line",
        reuseOnQueryChange: true,
        hideSidebar: true,
        showLink: false
      }
    },
    {
      // 保留旧地址，按内容进入首页或工作台。
      path: "/personal-workbench",
      name: "PersonalWorkbench",
      redirect: to => ({
        path: ["messages", "notices", "announcements"].includes(
          String(to.query.tab)
        )
          ? "/welcome"
          : "/workbench",
        query: to.query
      }),
      meta: {
        title: "待办与收藏",
        showLink: false
      }
    },
    {
      path: "/welcome",
      name: "Welcome",
      component: () => import("@/views/home/index.vue"),
      meta: {
        title: $t("menus.pureHome"),
        icon: "ri:home-4-line",
        reuseOnQueryChange: true,
        hideSidebar: true,
        showLink: VITE_HIDE_HOME === "true" ? false : true
      }
    }
  ]
} satisfies RouteConfigsTable;
