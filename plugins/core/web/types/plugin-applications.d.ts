declare module "virtual:plugin-applications" {
  const applications: {
    title: string;
    summary: string;
    icon: string;
    path: string;
    rootPath: string;
    tone: "blue" | "cyan" | "violet" | "green" | "orange" | "rose";
  }[];
  export default applications;
}

declare module "virtual:business-route-roots" {
  const roots: string[];
  export default roots;
}

declare module "virtual:platform-workbench" {
  const component: () => Promise<import("vue").Component>;
  export default component;
}

declare module "virtual:workflow-routes" {
  const routes: Record<string, string>;
  export default routes;
}

declare module "virtual:sidebar-layouts" {
  const layouts: import("../src/router/sidebarLayout").SidebarLayout[];
  export const sidebarIcons: Record<string, string>;
  export default layouts;
}
