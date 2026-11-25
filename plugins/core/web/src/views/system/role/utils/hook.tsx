import dayjs from "dayjs";
import editForm from "../form.vue";
import { message } from "@/utils/message";
import { ElMessageBox } from "element-plus";
import { usePublicHooks } from "../../hooks";
import { addDialog } from "@/components/ReDialog";
import type { FormItemProps } from "../utils/types";
import type { PaginationProps } from "@pureadmin/table";
import { deviceDetection } from "@pureadmin/utils";
import { getMenuTree } from "@/api/system";
import sidebarLayouts from "virtual:sidebar-layouts";
import { buildRoleMenuCatalog } from "./menuCatalog";
import { getDictionaryOptions } from "@/api/systemDictionary";
import {
  batchSyncRoleMenus,
  batchSyncRolePermissions,
  createRole,
  dataScopeLabel,
  deleteRole,
  fetchRoleMenuIds,
  getRolePermissionConfig,
  listRoles,
  updateRole,
  type RoleDataScope,
  type RolePayload,
  type SystemPermission,
  type SystemRoleRow
} from "@/api/systemRole";
import { MINIAPP_PORTALS } from "@/api/miniappMenu";
import {
  batchSyncRoleMiniappMenus,
  getRoleMiniappMenuCatalog,
  getRoleMiniappMenuConfig,
  type MiniappMenuGroup,
  type MiniappPortal
} from "@/api/roleMiniappMenu";
import {
  buildPermissionGroups,
  formatPermissionModuleLabel
} from "./permissionModules";
import {
  menuCheckState,
  toggleMenuSubtree,
  type MenuSelectionNode
} from "./menuSelection";
import { type Ref, computed, reactive, ref, onMounted, h, watch } from "vue";

function errorText(error: unknown, fallback: string) {
  const anyError = error as any;
  return (
    anyError?.response?.data?.message ||
    anyError?.response?.data?.detail ||
    anyError?.message ||
    fallback
  );
}

function emptyPortalRecord<T>(make: () => T): Record<MiniappPortal, T> {
  return Object.fromEntries(
    MINIAPP_PORTALS.map(item => [item.value, make()])
  ) as Record<MiniappPortal, T>;
}

export function useRole(treeRef: Ref) {
  const form = reactive({
    role_name: "",
    role_no: "",
    is_active: "" as "" | "true" | "false"
  });
  const curRow = ref<SystemRoleRow | null>(null);
  const formRef = ref();
  const dataList = ref<SystemRoleRow[]>([]);
  const treeIds = ref<string[]>([]);
  const treeData = ref<MenuSelectionNode[]>([]);
  const isShow = ref(false);
  const loading = ref(true);
  const treeSearchValue = ref();
  const switchLoadMap = ref({});
  const isExpandAll = ref(false);
  const bindTab = ref<"menu" | "api" | "miniapp">("menu");
  const pendingMenuIds = ref<string[]>([]);
  const menuLoading = ref(false);
  const menuSaving = ref(false);
  const menuLoaded = ref(false);
  const menuCatalogLoaded = ref(false);
  const menuReady = computed(
    () => menuLoaded.value && menuCatalogLoaded.value && !menuLoading.value
  );
  const isSelectAll = computed({
    get: () =>
      treeIds.value.length > 0 &&
      treeIds.value.every(id => pendingMenuIds.value.includes(id)),
    set: (checked: boolean) => {
      if (!menuReady.value || menuSaving.value) return;
      pendingMenuIds.value = checked ? [...treeIds.value] : [];
    }
  });
  let menuLoadSequence = 0;
  const permLoading = ref(false);
  const permSaving = ref(false);
  const permCatalog = ref<SystemPermission[]>([]);
  const permChecked = ref<string[]>([]);
  const permScopes = reactive<Record<string, RoleDataScope>>({});
  const permKeyword = ref("");
  const permModule = ref("");
  const roleDataScope = ref<RoleDataScope>("organization");
  const advancedScope = ref(false);
  const miniLoading = ref(false);
  const miniSaving = ref(false);
  const miniPortal = ref<MiniappPortal>(MINIAPP_PORTALS[0].value);
  const miniCatalog = reactive<Record<MiniappPortal, MiniappMenuGroup[]>>(
    emptyPortalRecord<MiniappMenuGroup[]>(() => [])
  );
  /** 选中的小程序菜单 id（跨门户） */
  const miniChecked = ref<string[]>([]);
  const dataScopeOptions: Array<{ label: string; value: RoleDataScope }> = [
    { label: dataScopeLabel("all"), value: "all" },
    { label: dataScopeLabel("organization"), value: "organization" },
    { label: dataScopeLabel("department"), value: "department" },
    { label: dataScopeLabel("self"), value: "self" },
    { label: dataScopeLabel("related"), value: "related" }
  ];
  const { switchStyle } = usePublicHooks();
  const treeProps = {
    value: "id",
    label: "title",
    children: "children"
  };
  const pagination = reactive<PaginationProps>({
    total: 0,
    pageSize: 20,
    currentPage: 1,
    background: true
  });
  const columns: TableColumnList = [
    { label: "角色名称", prop: "role_name" },
    { label: "角色编号", prop: "role_no" },
    {
      label: "数据范围",
      prop: "data_scope_code",
      formatter: ({ data_scope_code }) => dataScopeLabel(data_scope_code)
    },
    {
      label: "内置",
      prop: "is_builtin",
      width: 70,
      formatter: ({ is_builtin }) => (is_builtin ? "是" : "否")
    },
    { label: "用户数", prop: "user_count", width: 80 },
    { label: "权限数", prop: "permission_count", width: 80 },
    {
      label: "状态",
      cellRenderer: scope => (
        <el-switch
          size={scope.props.size === "small" ? "small" : "default"}
          loading={switchLoadMap.value[scope.row.id]?.loading}
          disabled={scope.row.is_builtin}
          v-model={scope.row.is_active}
          active-text="已启用"
          inactive-text="已停用"
          inline-prompt
          style={switchStyle.value}
          onChange={() => onChange(scope.row)}
        />
      ),
      minWidth: 90
    },
    { label: "说明", prop: "description", minWidth: 160 },
    {
      label: "更新时间",
      prop: "updated_at",
      minWidth: 160,
      formatter: ({ updated_at }) =>
        updated_at ? dayjs(updated_at).format("YYYY-MM-DD HH:mm:ss") : "—"
    },
    { label: "操作", fixed: "right", width: 210, slot: "operation" }
  ];
  // const buttonClass = computed(() => {
  //   return [
  //     "h-5!",
  //     "reset-margin",
  //     "text-gray-500!",
  //     "dark:text-white!",
  //     "dark:hover:text-primary!"
  //   ];
  // });

  function onChange(row: SystemRoleRow) {
    ElMessageBox.confirm(
      `确认要<strong>${row.is_active ? "启用" : "停用"}</strong><strong style='color:var(--el-color-primary)'>${row.role_name}</strong>吗?`,
      "系统提示",
      {
        confirmButtonClass: row.is_active
          ? "app-button-success"
          : "app-button-warning",
        confirmButtonText: "确定",
        cancelButtonText: "取消",
        type: "warning",
        dangerouslyUseHTMLString: true,
        draggable: true
      }
    )
      .then(async () => {
        switchLoadMap.value[row.id] = { loading: true };
        try {
          await updateRole(row.id, { is_active: row.is_active });
          message(`已${row.is_active ? "启用" : "停用"}${row.role_name}`, {
            type: "success"
          });
        } catch (error) {
          row.is_active = !row.is_active;
          message(errorText(error, "角色状态修改失败"), { type: "error" });
        } finally {
          switchLoadMap.value[row.id] = { loading: false };
        }
      })
      .catch(() => {
        row.is_active = !row.is_active;
      });
  }

  async function handleDelete(row: SystemRoleRow) {
    try {
      await deleteRole(row.id);
    } catch (error) {
      message(errorText(error, "删除角色失败"), { type: "error" });
      return;
    }
    if (curRow.value?.id === row.id) handleMenu();
    message(`已删除角色「${row.role_name}」`, { type: "success" });
    await onSearch();
  }

  function handleSizeChange(val: number) {
    pagination.pageSize = val;
    pagination.currentPage = 1;
    onSearch();
  }

  function handleCurrentChange(val: number) {
    pagination.currentPage = val;
    onSearch();
  }

  function handleSelectionChange(_val) {}

  async function onSearch() {
    loading.value = true;
    try {
      const res = await listRoles({
        role_name: form.role_name.trim() || undefined,
        role_no: form.role_no.trim() || undefined,
        is_active:
          form.is_active === "" ? undefined : form.is_active === "true",
        page: pagination.currentPage,
        page_size: pagination.pageSize
      });
      dataList.value = res.data?.items ?? [];
      pagination.total = res.data?.total ?? 0;
    } catch (error) {
      message(errorText(error, "加载角色失败"), { type: "error" });
    } finally {
      loading.value = false;
    }
  }

  const resetForm = formEl => {
    if (!formEl) return;
    formEl.resetFields();
    pagination.currentPage = 1;
    onSearch();
  };

  function openDialog(title = "新增", row?: SystemRoleRow) {
    addDialog({
      title: `${title}角色`,
      props: {
        formInline: {
          id: row?.id,
          role_no: row?.role_no ?? "",
          role_name: row?.role_name ?? "",
          description: row?.description ?? "",
          data_scope_code: row?.data_scope_code ?? "organization",
          is_active: row?.is_active ?? true,
          is_builtin: row?.is_builtin ?? false
        } satisfies FormItemProps
      },
      width: "40%",
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
          const payload: RolePayload = {
            role_no: curData.role_no.trim(),
            role_name: curData.role_name.trim(),
            description: curData.description || null,
            data_scope_code: curData.data_scope_code,
            is_active: curData.is_active
          };
          try {
            if (curData.id) await updateRole(curData.id, payload);
            else await createRole(payload);
          } catch (error) {
            message(errorText(error, `${title}角色失败`), { type: "error" });
            return;
          }
          message(`已${title}角色「${payload.role_name}」`, {
            type: "success"
          });
          done();
          if (title === "新增") pagination.currentPage = 1;
          await onSearch();
        });
      }
    });
  }

  const permCheckedSet = computed(() => new Set(permChecked.value));
  const permissionModuleLabels = ref<Record<string, string>>({});
  const permModuleOptions = computed(() => {
    const modules = new Set<string>();
    for (const item of permCatalog.value) {
      modules.add(item.module_code || "其他");
    }
    return [...modules]
      .sort((a, b) =>
        formatPermissionModuleLabel(
          a,
          permissionModuleLabels.value
        ).localeCompare(
          formatPermissionModuleLabel(b, permissionModuleLabels.value),
          "zh-CN"
        )
      )
      .map(module => ({
        value: module,
        label: formatPermissionModuleLabel(module, permissionModuleLabels.value)
      }));
  });
  const permGroups = computed(() => {
    const keyword = permKeyword.value.trim().toLowerCase();
    return buildPermissionGroups(
      permCatalog.value,
      permissionModuleLabels.value
    )
      .map(group => ({
        ...group,
        items: group.items.filter(item => {
          if (
            permModule.value &&
            (item.module_code || "其他") !== permModule.value
          ) {
            return false;
          }
          if (!keyword) return true;
          return (
            item.permission_name.toLowerCase().includes(keyword) ||
            item.permission_key.toLowerCase().includes(keyword) ||
            (item.module_code || "").toLowerCase().includes(keyword) ||
            group.moduleLabel.toLowerCase().includes(keyword)
          );
        })
      }))
      .filter(group => group.items.length > 0);
  });

  function ensurePermScope(permissionId: string) {
    if (!permScopes[permissionId]) {
      permScopes[permissionId] = roleDataScope.value;
    }
  }

  function togglePermission(permissionId: string, selected: boolean) {
    if (selected) {
      if (!permChecked.value.includes(permissionId)) {
        permChecked.value = [...permChecked.value, permissionId];
      }
      ensurePermScope(permissionId);
      return;
    }
    permChecked.value = permChecked.value.filter(id => id !== permissionId);
  }

  function togglePermGroup(items: SystemPermission[], select: boolean) {
    const ids = new Set(permChecked.value);
    for (const item of items) {
      if (select) {
        ids.add(item.id);
        ensurePermScope(item.id);
      } else {
        ids.delete(item.id);
      }
    }
    permChecked.value = [...ids];
  }

  function isPermGroupChecked(items: SystemPermission[]) {
    return (
      items.length > 0 && items.every(item => permCheckedSet.value.has(item.id))
    );
  }

  async function loadPermissionBind(roleId: string) {
    permLoading.value = true;
    try {
      const res = await getRolePermissionConfig(roleId);
      if (res.code !== 0) throw new Error(res.message || "接口权限加载失败");
      roleDataScope.value = res.data.role.data_scope_code || "organization";
      permCatalog.value = res.data.permissions.map(item => ({
        id: item.id,
        permission_key: item.permission_key,
        permission_name: item.permission_name,
        module_code: item.module_code
      }));
      permChecked.value = res.data.permissions
        .filter(item => item.selected)
        .map(item => item.id);
      for (const key of Object.keys(permScopes)) delete permScopes[key];
      for (const item of res.data.permissions) {
        if (item.selected) {
          permScopes[item.id] = item.data_scope_code || roleDataScope.value;
        }
      }
    } catch (error) {
      message((error as Error).message || "接口权限加载失败", {
        type: "error"
      });
    } finally {
      permLoading.value = false;
    }
  }

  async function savePermissions() {
    const roleId = curRow.value?.id;
    if (!roleId) return;
    permSaving.value = true;
    try {
      const res = await batchSyncRolePermissions({
        role_id: roleId,
        permission_scopes: permChecked.value.map(permissionId => ({
          permission_id: permissionId,
          data_scope_code:
            permScopes[permissionId] &&
            permScopes[permissionId] !== roleDataScope.value
              ? permScopes[permissionId]
              : null
        }))
      });
      if (res.code !== 0) throw new Error(res.message || "接口权限保存失败");
      message(`角色「${curRow.value.role_name}」的接口权限修改成功`, {
        type: "success"
      });
    } catch (error) {
      message(errorText(error, "接口权限保存失败"), {
        type: "error"
      });
    } finally {
      permSaving.value = false;
    }
  }

  const miniPortalOptions = MINIAPP_PORTALS;
  const miniCheckedSet = computed(() => new Set(miniChecked.value));
  const currentMiniGroups = computed(() => miniCatalog[miniPortal.value] ?? []);

  function portalIds(portal: MiniappPortal) {
    return (miniCatalog[portal] ?? []).flatMap(group =>
      group.items.map(item => item.id)
    );
  }

  function portalCheckedCount(portal: MiniappPortal) {
    return portalIds(portal).filter(id => miniCheckedSet.value.has(id)).length;
  }

  function toggleMiniItem(id: string, selected: boolean) {
    const current = new Set(miniChecked.value);
    if (selected) current.add(id);
    else current.delete(id);
    miniChecked.value = [...current];
  }

  function toggleMiniGroup(ids: string[], select: boolean) {
    const current = new Set(miniChecked.value);
    for (const id of ids) {
      if (select) current.add(id);
      else current.delete(id);
    }
    miniChecked.value = [...current];
  }

  function toggleMiniPortal(portal: MiniappPortal, select: boolean) {
    toggleMiniGroup(portalIds(portal), select);
  }

  async function loadMiniappBind(roleId: string) {
    miniLoading.value = true;
    try {
      const [catalogRes, configRes] = await Promise.all([
        getRoleMiniappMenuCatalog(),
        getRoleMiniappMenuConfig(roleId)
      ]);
      for (const portal of MINIAPP_PORTALS) {
        miniCatalog[portal.value] =
          catalogRes.data?.portals?.[portal.value] ?? [];
      }
      miniChecked.value = configRes.data?.miniapp_menu_ids ?? [];
    } catch (error) {
      message(errorText(error, "小程序菜单加载失败"), { type: "error" });
    } finally {
      miniLoading.value = false;
    }
  }

  async function saveMiniappMenus() {
    const roleId = curRow.value?.id;
    if (!roleId) return;
    miniSaving.value = true;
    try {
      await batchSyncRoleMiniappMenus({
        role_id: roleId,
        miniapp_menu_ids: miniChecked.value
      });
      message(`角色「${curRow.value.role_name}」的小程序菜单修改成功`, {
        type: "success"
      });
    } catch (error) {
      message(errorText(error, "小程序菜单保存失败"), { type: "error" });
    } finally {
      miniSaving.value = false;
    }
  }

  /** 打开角色的菜单、接口、小程序菜单绑定 */
  async function handleMenu(row?: SystemRoleRow) {
    const id = row?.id;
    if (id) {
      const sequence = ++menuLoadSequence;
      curRow.value = row;
      bindTab.value = "menu";
      permKeyword.value = "";
      permModule.value = "";
      isShow.value = true;
      pendingMenuIds.value = [];
      menuLoaded.value = false;
      menuLoading.value = true;
      try {
        const menuIds = await fetchRoleMenuIds(id);
        if (sequence !== menuLoadSequence || !isShow.value) return;
        pendingMenuIds.value = menuIds;
        menuLoaded.value = true;
      } catch (error) {
        if (sequence !== menuLoadSequence) return;
        message(errorText(error, "菜单权限加载失败"), { type: "error" });
      } finally {
        if (sequence === menuLoadSequence) menuLoading.value = false;
      }
      await Promise.all([loadPermissionBind(id), loadMiniappBind(id)]);
    } else {
      curRow.value = null;
      isShow.value = false;
    }
  }

  /** 高亮当前权限选中行 */
  function rowStyle({ row: { id } }) {
    return {
      cursor: "pointer",
      background: id === curRow.value?.id ? "var(--el-fill-color-light)" : ""
    };
  }

  /** 菜单权限-保存 */
  async function handleSave() {
    if (!curRow.value || !menuReady.value || menuSaving.value) return;
    const { id, role_name } = curRow.value;
    menuSaving.value = true;
    try {
      // 历史绑定可能含已退役/未启用插件菜单；只保存当前目录内的勾选，服务端保留范围外绑定。
      const catalogIds = new Set(treeIds.value);
      await batchSyncRoleMenus({
        role_id: id,
        menu_ids: [
          ...new Set(pendingMenuIds.value.filter(menuId => catalogIds.has(menuId)))
        ]
      });
    } catch (error) {
      message(errorText(error, "菜单权限修改失败"), { type: "error" });
      return;
    } finally {
      menuSaving.value = false;
    }
    message(`角色「${role_name}」的菜单权限修改成功`, { type: "success" });
  }

  /** 数据权限 可自行开发 */
  // function handleDatabase() {}

  const onQueryChanged = (query: string) => {
    treeRef.value!.filter(query);
  };

  const filterMethod = (query: string, node) => {
    return String(node.title ?? "").includes(query);
  };

  onMounted(async () => {
    onSearch();
    void getDictionaryOptions(["sys_module"], true)
      .then(res => {
        permissionModuleLabels.value = Object.fromEntries(
          (res.data.sys_module || []).map(item => [
            item.item_code,
            item.item_name
          ])
        );
      })
      .catch(() => {
        message("权限模块中文名称加载失败，可刷新页面重试", {
          type: "warning"
        });
      });
    try {
      const res = await getMenuTree();
      const { tree, menuIds } = buildRoleMenuCatalog(res.data ?? [], sidebarLayouts);
      treeIds.value = menuIds;
      treeData.value = tree;
      menuCatalogLoaded.value = true;
    } catch (error) {
      message(errorText(error, "加载菜单失败"), { type: "error" });
    }
  });

  function menuState(node: MenuSelectionNode) {
    return menuCheckState(node, pendingMenuIds.value);
  }

  function toggleMenu(node: MenuSelectionNode, checked: boolean) {
    if (!menuReady.value || menuSaving.value) return;
    pendingMenuIds.value = toggleMenuSubtree(
      pendingMenuIds.value,
      node,
      checked
    );
  }

  watch(isExpandAll, val => {
    const keys = (nodes: MenuSelectionNode[]): string[] =>
      nodes.flatMap(node => [node.id, ...keys(node.children)]);
    treeRef.value?.setExpandedKeys(val ? keys(treeData.value) : []);
  });

  return {
    form,
    isShow,
    curRow,
    loading,
    columns,
    rowStyle,
    dataList,
    treeData,
    treeProps,
    menuLoading,
    menuSaving,
    menuReady,
    menuState,
    toggleMenu,
    pagination,
    isExpandAll,
    isSelectAll,
    treeSearchValue,
    // buttonClass,
    bindTab,
    permLoading,
    permSaving,
    permGroups,
    permCheckedSet,
    permScopes,
    permKeyword,
    permModule,
    permModuleOptions,
    roleDataScope,
    advancedScope,
    dataScopeOptions,
    dataScopeLabel,
    miniLoading,
    miniSaving,
    miniCatalog,
    miniChecked,
    miniCheckedSet,
    miniPortal,
    miniPortalOptions,
    currentMiniGroups,
    portalCheckedCount,
    togglePermission,
    togglePermGroup,
    isPermGroupChecked,
    savePermissions,
    toggleMiniItem,
    toggleMiniGroup,
    toggleMiniPortal,
    portalIds,
    saveMiniappMenus,
    onSearch,
    resetForm,
    openDialog,
    handleMenu,
    handleSave,
    handleDelete,
    filterMethod,
    onQueryChanged,
    // handleDatabase,
    handleSizeChange,
    handleCurrentChange,
    handleSelectionChange
  };
}
