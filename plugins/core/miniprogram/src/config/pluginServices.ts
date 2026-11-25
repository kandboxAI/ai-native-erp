/** 插件入口协议；教育身份等展示规则由所属提供器维护。 */
export type ServiceTone = "blue" | "purple" | "orange" | "green";
export interface RoleServiceItem {
  title: string;
  desc: string;
  /** 本地 PNG 路径；行业图标保存在所属插件的 static/<key>/ 下。 */
  icon: string;
  tone: ServiceTone;
  url?: string;
  tab?: string;
}
export interface RoleServiceOptions {
  role: string;
  department: string;
  homeroomTeacher: boolean;
  pendingCount?: number;
  permissions?: string[];
}
export interface PluginSecondTab {
  label: string;
  path: string;
  kind: "attendance" | "material" | "workspace";
}
/** 业务待办由所属插件读取，外壳只负责分页和跳转。 */
export interface InboxTodoRow {
  avatar_url?: string | null;
  id: string;
  task_name: string;
  business_summary: string;
  arrived_at: string | null;
  target?: string;
  business_display_type: string;
}
export interface InboxTodoPage {
  items: InboxTodoRow[];
  total: number;
  page: number;
  page_size: number;
}
export interface MiniappServiceProvider {
  key: string;
  getRoleServiceItems(options: RoleServiceOptions): RoleServiceItem[];
  /** 仅提供本插件菜单的展示图标，不决定入口授权。 */
  getServiceIcon?(path: string): string | undefined;
  /** 本插件页面的用途说明；仅用于展示和搜索，不决定入口授权。 */
  getServiceDescription?(path: string): string | undefined;
  getSecondTab?(options: RoleServiceOptions): PluginSecondTab | undefined;
  listTodos?(page: number, pageSize: number): Promise<InboxTodoPage>;
  /** 插件解释自己的业务通知链接；外壳不新增行业路径映射。 */
  notificationTarget?(item: { redirect_url?: string; scene_key?: string }): string | undefined;
}
