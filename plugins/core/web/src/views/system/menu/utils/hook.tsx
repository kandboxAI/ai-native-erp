import editForm from "../form.vue";
import { message } from "@/utils/message";
import {
  createMenu,
  deleteMenu,
  getMenuTree,
  updateMenu,
  type MenuNode,
  type MenuPayload
} from "@/api/system";
import { listPermissions } from "@/api/systemPermission";
import { addDialog } from "@/components/ReDialog";
import { computed, reactive, ref, onMounted, h } from "vue";
import type { FormItemProps } from "../utils/types";
import { menuTypeLabel } from "./enums";
import { useRenderIcon } from "@/components/ReIcon/src/hooks";
import { cloneDeep, isAllEmpty, deviceDetection } from "@pureadmin/utils";
import { usePermissionStoreHook } from "@/store/modules/permission";
import { transformI18n } from "@/plugins/i18n";
import type { RouteRecordRaw } from "vue-router";

const MENU_TYPE_TAG = { directory: "warning", menu: "primary", button: "info" };

function errorText(error: unknown, fallback: string) {
  const anyError = error as any;
  return (
    anyError?.response?.data?.message ||
    anyError?.response?.data?.detail ||
    anyError?.message ||
    fallback
  );
}

function filterTree(nodes: MenuNode[], keyword: string): MenuNode[] {
  return nodes
    .map(node => ({
      ...node,
      children: filterTree(node.children ?? [], keyword)
    }))
    .filter(
      node =>
        node.menu_name.includes(keyword) ||
        node.menu_key.includes(keyword) ||
        (node.path ?? "").includes(keyword) ||
        (node.component ?? "").includes(keyword) ||
        (node.children?.length ?? 0) > 0
    );
}

export function useMenu() {
  const permissionStore = usePermissionStoreHook();
  const form = reactive({ menu_name: "" });

  const formRef = ref();
  const menuTree = ref<MenuNode[]>([]);
  const keyword = ref("");
  const menuView = ref<"sidebar" | "directory">("sidebar");
  const menuById = computed(() => {
    const items = new Map<string, MenuNode>();
    function visit(nodes: MenuNode[]) {
      for (const node of nodes) {
        items.set(node.id, node);
        visit(node.children ?? []);
      }
    }
    visit(menuTree.value);
    return items;
  });
  const menuByKey = computed(() =>
    new Map([...menuById.value.values()].map(menu => [menu.menu_key, menu]))
  );
  const dataList = computed(() => {
    const project = (nodes: RouteRecordRaw[]): MenuNode[] =>
      nodes.map(node => {
        // SidebarItem displays an only leaf child in place of its parent.
        const onlyChild = node.children?.length === 1 ? node.children[0] : undefined;
        const display = onlyChild && !onlyChild.children && !node.meta?.showParent
          && !onlyChild.meta?.showParent ? onlyChild : node;
        const key = display.meta?.menuKey;
        const menu = typeof key === "string" ? menuByKey.value.get(key) : undefined;
        return {
          ...menu,
          id: menu?.id ?? `group:${display.path}`,
          menu_name: transformI18n(display.meta?.title) || menu?.menu_name || "",
          menu_key: menu?.menu_key ?? "",
          icon: display.meta?.sidebarIcon ?? display.meta?.icon ?? menu?.icon,
          menu_type_code: menu?.menu_type_code ?? "directory",
          children: project(display.children ?? [])
        } as MenuNode;
      });
    const tree = menuView.value === "sidebar"
      ? project(permissionStore.sidebarMenus)
      : menuTree.value;
    return keyword.value ? filterTree(tree, keyword.value) : tree;
  });
  const isStoredMenu = (id: string) => menuById.value.has(id);
  const loading = ref(true);
  const permissionOptions = ref<Array<{ value: string; label: string }>>([]);

  const columns: TableColumnList = [
    {
      label: "菜单名称",
      prop: "menu_name",
      align: "left",
      cellRenderer: ({ row }) => (
        <>
          <span class="inline-block mr-1">
            {row.icon
              ? h(useRenderIcon(row.icon), { style: { paddingTop: "1px" } })
              : null}
          </span>
          <span>{row.menu_name}</span>
        </>
      )
    },
    { label: "菜单标识", prop: "menu_key" },
    {
      label: "类型",
      prop: "menu_type_code",
      width: 90,
      cellRenderer: ({ row, props }) => (
        <el-tag
          size={props.size}
          type={MENU_TYPE_TAG[row.menu_type_code] as any}
          effect="plain"
        >
          {menuTypeLabel(row.menu_type_code)}
        </el-tag>
      )
    },
    {
      label: "路由路径",
      prop: "path",
      formatter: ({ path, external_url, is_external }) =>
        is_external ? external_url : path
    },
    {
      label: "组件路径",
      prop: "component",
      formatter: ({ component }) => (isAllEmpty(component) ? "—" : component)
    },
    {
      label: "重定向",
      prop: "redirect",
      formatter: ({ flex_form }) => flex_form?.route?.redirect || "—"
    },
    {
      label: "页面参数",
      prop: "route_meta",
      minWidth: 180,
      formatter: ({ flex_form }) => {
        const meta = flex_form?.route?.meta;
        return meta && Object.keys(meta).length ? JSON.stringify(meta) : "—";
      }
    },
    {
      label: "所需权限",
      prop: "permission_key",
      formatter: ({ permission_key }) => permission_key || "—"
    },
    { label: "排序", prop: "sort_no", width: 80 },
    {
      label: "显示",
      prop: "is_visible",
      formatter: ({ id, is_visible }) => isStoredMenu(id) ? (is_visible ? "是" : "否") : "—",
      width: 70
    },
    {
      label: "状态",
      prop: "is_active",
      width: 80,
      cellRenderer: ({ row, props }) => (
        isStoredMenu(row.id)
          ? <el-tag size={props.size} type={row.is_active ? "success" : "danger"}>
              {row.is_active ? "启用" : "停用"}
            </el-tag>
          : "—"
      )
    },
    { label: "操作", fixed: "right", width: 210, slot: "operation" }
  ];

  function handleSelectionChange(_val) {}

  function resetForm(formEl) {
    if (!formEl) return;
    formEl.resetFields();
    onSearch();
  }

  async function loadPermissionOptions() {
    try {
      const res = await listPermissions({
        page: 1,
        page_size: 1000,
        is_active: true
      });
      permissionOptions.value = (res.data?.items ?? []).map(item => ({
        value: item.permission_key,
        label: `${item.permission_name}（${item.permission_key}）`
      }));
    } catch {
      permissionOptions.value = [];
    }
  }

  async function onSearch() {
    loading.value = true;
    try {
      const res = await getMenuTree();
      menuTree.value = res.data ?? [];
      keyword.value = String(form.menu_name ?? "").trim();
    } catch (error) {
      message(errorText(error, "加载菜单失败"), { type: "error" });
    } finally {
      loading.value = false;
    }
  }

  function higherMenuOptions(excludeId?: string) {
    const strip = (nodes: MenuNode[]): MenuNode[] =>
      nodes
        .filter(
          node => node.id !== excludeId && node.menu_type_code !== "button"
        )
        .map(node => ({ ...node, children: strip(node.children ?? []) }));
    return strip(cloneDeep(menuTree.value));
  }

  function openDialog(title = "新增", row?: Partial<MenuNode>) {
    const editing = title === "修改";
    if (editing && row?.id) row = menuById.value.get(row.id);
    addDialog({
      title: `${title}菜单`,
      props: {
        formInline: {
          id: editing ? row?.id : undefined,
          menu_key: editing ? (row?.menu_key ?? "") : "",
          menu_name: editing ? (row?.menu_name ?? "") : "",
          menu_type_code: editing ? (row?.menu_type_code ?? "menu") : "menu",
          parent_id: row?.parent_id ?? null,
          path: editing ? (row?.path ?? "") : "",
          component: editing ? (row?.component ?? "") : "",
          route_redirect: editing
            ? (row?.flex_form?.route?.redirect ?? "")
            : "",
          route_meta: editing
            ? JSON.stringify(row?.flex_form?.route?.meta ?? {}, null, 2)
            : "{}",
          flex_form: editing ? cloneDeep(row?.flex_form ?? {}) : {},
          icon: editing ? (row?.icon ?? "") : "",
          permission_key: editing ? (row?.permission_key ?? "") : "",
          is_external: editing ? Boolean(row?.is_external) : false,
          external_url: editing ? (row?.external_url ?? "") : "",
          open_target_code: (editing && row?.open_target_code) || "self",
          sort_no: editing ? (row?.sort_no ?? 0) : 0,
          is_visible: editing ? row?.is_visible !== false : true,
          is_active: editing ? row?.is_active !== false : true,
          remark: editing ? (row?.remark ?? "") : "",
          higherMenuOptions: higherMenuOptions(row?.id) as any,
          permissionOptions: permissionOptions.value
        } satisfies FormItemProps
      },
      width: "65%",
      draggable: true,
      fullscreen: deviceDetection(),
      fullscreenIcon: true,
      closeOnClickModal: false,
      contentRenderer: () => h(editForm, { ref: formRef, formInline: null }),
      beforeSure: (done, { options }) => {
        const FormRef = formRef.value.getRef();
        const curData = options.props.formInline as FormItemProps;
        FormRef.validate(async valid => {
          if (!valid) return;
          let routeMeta: Record<string, unknown>;
          try {
            routeMeta = JSON.parse(curData.route_meta || "{}");
            if (
              routeMeta === null ||
              Array.isArray(routeMeta) ||
              typeof routeMeta !== "object"
            ) {
              throw new Error("页面参数必须是 JSON 对象");
            }
          } catch (error) {
            message(errorText(error, "页面参数不是有效的 JSON 对象"), {
              type: "error"
            });
            return;
          }
          const currentRoute = curData.flex_form?.route ?? {};
          const routeConfig = {
            ...currentRoute,
            meta: routeMeta,
            ...(curData.route_redirect
              ? { redirect: curData.route_redirect }
              : {})
          };
          if (!curData.route_redirect) delete routeConfig.redirect;
          const payload: MenuPayload = {
            menu_name: curData.menu_name.trim(),
            menu_type_code: curData.menu_type_code,
            parent_id: curData.parent_id || null,
            path: curData.path || null,
            component: curData.component || null,
            icon: curData.icon || null,
            permission_key: curData.permission_key || null,
            is_external: curData.is_external,
            external_url: curData.external_url || null,
            open_target_code: curData.open_target_code || null,
            sort_no: curData.sort_no,
            is_visible: curData.is_visible,
            is_active: curData.is_active,
            remark: curData.remark || null,
            flex_form: {
              ...(curData.flex_form ?? {}),
              route: routeConfig
            }
          };
          try {
            if (curData.id) {
              await updateMenu(curData.id, payload);
            } else {
              await createMenu({
                ...payload,
                menu_key: curData.menu_key.trim()
              });
            }
            message(`已${title}菜单「${payload.menu_name}」`, {
              type: "success"
            });
            done();
            await onSearch();
          } catch (error) {
            message(errorText(error, `${title}菜单失败`), { type: "error" });
          }
        });
      }
    });
  }

  async function handleDelete(row: MenuNode) {
    try {
      await deleteMenu(row.id);
      message(`已删除菜单「${row.menu_name}」`, { type: "success" });
      await onSearch();
    } catch (error) {
      message(errorText(error, "删除菜单失败"), { type: "error" });
    }
  }

  onMounted(async () => {
    await Promise.all([onSearch(), loadPermissionOptions()]);
  });

  return {
    form,
    loading,
    columns,
    dataList,
    menuView,
    isStoredMenu,
    onSearch,
    resetForm,
    openDialog,
    handleDelete,
    handleSelectionChange
  };
}
