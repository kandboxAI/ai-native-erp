export type AppTabKey =
  | "home"
  | "secondary"
  | "xiaohang"
  | "messages"
  | "profile";

export interface AppTabItem {
  key: AppTabKey;
  label: string;
  path: string;
  icon?: string;
  iconActive?: string;
}

export const workspaceTab: AppTabItem = {
  key: "secondary",
  label: "应用",
  path: "/pages/workspace/index",
  icon: "/static/tabbar/applications.png",
  iconActive: "/static/tabbar/applications-active.png",
};

/** 所有账号共用固定导航；业务入口由工作台的授权菜单承载。 */
export function buildAppTabs(): AppTabItem[] {
  return [
    {
      key: "home",
      label: "常用",
      path: "/pages/home/index",
      icon: "/static/tabbar/favorites.png",
      iconActive: "/static/tabbar/favorites-active.png",
    },
    {
      key: "messages",
      label: "待办",
      path: "/pages/messages/index",
      icon: "/static/tabbar/tasks.png",
      iconActive: "/static/tabbar/tasks-active.png",
    },
    {
      key: "xiaohang",
      label: "智能助手",
      path: "/pages/xiaohang/index",
    },
    workspaceTab,
    {
      key: "profile",
      label: "我的",
      path: "/pages/profile/index",
      icon: "/static/tabbar/account.png",
      iconActive: "/static/tabbar/account-active.png",
    },
  ];
}
