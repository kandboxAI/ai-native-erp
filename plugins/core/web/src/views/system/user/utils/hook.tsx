import "./reset.css";
import dayjs from "dayjs";
import roleForm from "../form/role.vue";
import editForm from "../form/index.vue";
import { handleTree } from "@/utils/tree";
import { message } from "@/utils/message";
import userAvatar from "@/assets/user.jpg";
import { usePublicHooks } from "../../hooks";
import { ZxcvbnFactory } from "@zxcvbn-ts/core";
import { addDialog } from "@/components/ReDialog";
import type { PaginationProps } from "@pureadmin/table";
import type { FormItemProps, OrgDeptNode, RoleFormItemProps } from "./types";
import { isAllEmpty, hideTextAtIndex, deviceDetection } from "@pureadmin/utils";
import { fetchAllDepartments, getOrganizationTree } from "@/api/system";
import type { OrganizationTreeNode } from "@/api/organizationStructure";
import { fetchAllRoles, type SystemRoleRow } from "@/api/systemRole";
import {
  createUserProfile,
  deleteUserProfile,
  listUserProfiles,
  resetUserProfilePassword,
  updateUserProfile,
  updateUserProfileStatus,
  type UserProfileRow
} from "@/api/systemUserProfile";
import {
  ElForm,
  ElInput,
  ElFormItem,
  ElProgress,
  ElMessageBox
} from "element-plus";
import { type Ref, h, ref, watch, computed, reactive, onMounted } from "vue";

function errorText(error: unknown, fallback: string) {
  const anyError = error as any;
  return (
    anyError?.response?.data?.message ||
    anyError?.response?.data?.detail ||
    anyError?.message ||
    fallback
  );
}

function flattenOrgs(nodes: OrganizationTreeNode[]) {
  const result: Array<{ id: string; org_name: string }> = [];
  const walk = (items: OrganizationTreeNode[]) =>
    items.forEach(item => {
      result.push({ id: item.id, org_name: item.org_name });
      walk(item.children ?? []);
    });
  walk(nodes);
  return result;
}

export function useUser(tableRef: Ref, treeRef: Ref) {
  const form = reactive({
    /** 左侧组织 / 部门树选中的节点 */
    org_id: "",
    department_id: "",
    keyword: "",
    mobile: "",
    is_active: "" as "" | "true" | "false"
  });
  const formRef = ref();
  const ruleFormRef = ref();
  const dataList = ref<UserProfileRow[]>([]);
  const loading = ref(true);
  const switchLoadMap = ref({});
  const { switchStyle } = usePublicHooks();
  const treeData = ref<OrgDeptNode[]>([]);
  const orgOptions = ref<Array<{ id: string; org_name: string }>>([]);
  const treeLoading = ref(true);
  const selectedNum = ref(0);
  const roleOptions = ref<SystemRoleRow[]>([]);
  const pagination = reactive<PaginationProps>({
    total: 0,
    pageSize: 20,
    currentPage: 1,
    background: true
  });
  const columns: TableColumnList = [
    {
      label: "勾选列",
      type: "selection",
      fixed: "left",
      reserveSelection: true
    },
    {
      label: "头像",
      prop: "avatar_url",
      cellRenderer: ({ row }) => (
        <el-image
          fit="cover"
          preview-teleported={true}
          src={row.avatar_url || userAvatar}
          preview-src-list={Array.of(row.avatar_url || userAvatar)}
          class="size-6 rounded-full align-middle"
        />
      ),
      width: 70
    },
    {
      label: "姓名",
      prop: "full_name",
      minWidth: 100,
      formatter: ({ full_name, display_name }) => full_name || display_name
    },
    { label: "显示名称", prop: "display_name", minWidth: 100 },
    {
      label: "登录邮箱",
      prop: "email",
      minWidth: 160,
      formatter: ({ email }) => email || "—"
    },
    {
      label: "手机号码",
      prop: "mobile",
      minWidth: 110,
      formatter: ({ mobile }) =>
        mobile ? hideTextAtIndex(mobile, { start: 3, end: 6 }) : "—"
    },
    { label: "组织", prop: "org_name", minWidth: 100 },
    {
      label: "部门",
      prop: "department_name",
      minWidth: 90,
      formatter: ({ department_name }) => department_name || "—"
    },
    {
      label: "角色",
      prop: "roles",
      minWidth: 140,
      cellRenderer: ({ row, props }) => (
        <>
          {(row.roles ?? []).map(role => (
            <el-tag size={props.size} class="mr-1" effect="plain">
              {role.role_name}
            </el-tag>
          ))}
        </>
      )
    },
    {
      label: "状态",
      prop: "is_active",
      minWidth: 90,
      cellRenderer: scope => (
        <el-switch
          size={scope.props.size === "small" ? "small" : "default"}
          loading={switchLoadMap.value[scope.row.id]?.loading}
          v-model={scope.row.is_active}
          active-text="已启用"
          inactive-text="已停用"
          inline-prompt
          style={switchStyle.value}
          onChange={() => onChange(scope.row)}
        />
      )
    },
    {
      label: "创建时间",
      minWidth: 150,
      prop: "created_at",
      formatter: ({ created_at }) =>
        created_at ? dayjs(created_at).format("YYYY-MM-DD HH:mm") : "—"
    },
    { label: "操作", fixed: "right", width: 180, slot: "operation" }
  ];
  const buttonClass = computed(() => ["h-5!", "reset-margin"]);
  const pwdForm = reactive({ newPwd: "" });
  const pwdProgress = [
    { color: "#e74242", text: "非常弱" },
    { color: "#EFBD47", text: "弱" },
    { color: "#ffa500", text: "一般" },
    { color: "#1bbf1b", text: "强" },
    { color: "#008000", text: "非常强" }
  ];
  const curScore = ref();
  const zxcvbnFactory = new ZxcvbnFactory();

  function userLabel(row: UserProfileRow) {
    return row.full_name || row.display_name;
  }

  function onChange(row: UserProfileRow) {
    ElMessageBox.confirm(
      `确认要<strong>${row.is_active ? "启用" : "停用"}</strong><strong style='color:var(--el-color-primary)'>${userLabel(row)}</strong>吗?`,
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
          await updateUserProfileStatus(row.id, row.is_active);
          message("已成功修改用户状态", { type: "success" });
        } catch (error) {
          row.is_active = !row.is_active;
          message(errorText(error, "用户状态修改失败"), { type: "error" });
        } finally {
          switchLoadMap.value[row.id] = { loading: false };
        }
      })
      .catch(() => {
        row.is_active = !row.is_active;
      });
  }

  async function handleDelete(row: UserProfileRow) {
    try {
      await deleteUserProfile(row.id);
      message(`已删除用户「${userLabel(row)}」`, { type: "success" });
      await onSearch();
    } catch (error) {
      message(errorText(error, "删除失败"), { type: "error" });
    }
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

  function handleSelectionChange(val) {
    selectedNum.value = val.length;
    tableRef.value.setAdaptive();
  }

  function onSelectionCancel() {
    selectedNum.value = 0;
    tableRef.value.getTableRef().clearSelection();
  }

  /** 批量删除 */
  async function onbatchDel() {
    const curSelected: UserProfileRow[] = tableRef.value
      .getTableRef()
      .getSelectionRows();
    const failed: string[] = [];
    for (const row of curSelected) {
      try {
        await deleteUserProfile(row.id);
      } catch (error) {
        failed.push(`${userLabel(row)}：${errorText(error, "删除失败")}`);
      }
    }
    if (failed.length) message(failed.join("；"), { type: "error" });
    else message(`已删除 ${curSelected.length} 个用户`, { type: "success" });
    tableRef.value.getTableRef().clearSelection();
    await onSearch();
  }

  async function onSearch() {
    loading.value = true;
    try {
      const res = await listUserProfiles({
        page: pagination.currentPage,
        page_size: pagination.pageSize,
        keyword: form.keyword.trim() || undefined,
        mobile: form.mobile.trim() || undefined,
        org_id: form.org_id || undefined,
        department_id: form.department_id || undefined,
        is_active: form.is_active === "" ? undefined : form.is_active === "true"
      });
      dataList.value = res.data?.items ?? [];
      pagination.total = res.data?.total ?? 0;
    } catch (error) {
      message(errorText(error, "加载用户失败"), { type: "error" });
    } finally {
      loading.value = false;
    }
  }

  const resetForm = formEl => {
    if (!formEl) return;
    formEl.resetFields();
    form.org_id = "";
    form.department_id = "";
    pagination.currentPage = 1;
    treeRef.value.onTreeReset();
    onSearch();
  };

  function onTreeSelect(node: OrgDeptNode & { selected: boolean }) {
    form.org_id = "";
    form.department_id = "";
    if (node.selected) {
      if (node.node_type === "dept") form.department_id = node.id;
      else form.org_id = node.id;
    }
    pagination.currentPage = 1;
    onSearch();
  }

  function openDialog(title = "新增", row?: UserProfileRow) {
    addDialog({
      title: `${title}用户`,
      props: {
        formInline: {
          id: row?.id,
          title,
          email: row?.email ?? "",
          mobile: row?.mobile ?? "",
          password: "",
          full_name: row?.full_name ?? row?.display_name ?? "",
          display_name: row?.display_name ?? "",
          org_id: row?.org_id ?? form.org_id ?? orgOptions.value[0]?.id ?? "",
          org_access_mode_code: row?.org_access_mode_code ?? "primary_only",
          org_ids: (row?.org_ids ?? []).filter(id => id !== row?.org_id),
          department_id: row?.department_id ?? (form.department_id || null),
          role_ids: (row?.roles ?? []).map(role => role.id),
          position_ids: [...(row?.position_ids ?? [])],
          is_active: row?.is_active ?? true,
          orgOptions: orgOptions.value,
          deptTree: treeData.value,
          roleOptions: roleOptions.value
        } satisfies FormItemProps
      },
      width: "52%",
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
          if (title === "新增" && !curData.email && !curData.mobile) {
            message("登录邮箱和手机号至少填写一个", { type: "warning" });
            return;
          }
          const common = {
            full_name: curData.full_name.trim(),
            display_name: curData.display_name.trim() || null,
            org_id: curData.org_id,
            org_access_mode_code: curData.org_access_mode_code,
            org_ids:
              curData.org_access_mode_code === "assigned"
                ? curData.org_ids
                : [],
            department_id: curData.department_id || null,
            role_ids: curData.role_ids,
            position_ids: curData.position_ids
          };
          try {
            if (curData.id) {
              await updateUserProfile(curData.id, common);
            } else {
              await createUserProfile({
                ...common,
                email: curData.email.trim() || null,
                mobile: curData.mobile.trim() || null,
                password: curData.password,
                is_active: curData.is_active
              });
            }
          } catch (error) {
            message(errorText(error, `${title}用户失败`), { type: "error" });
            return;
          }
          message(`已${title}用户「${common.full_name}」`, { type: "success" });
          done();
          if (title === "新增") pagination.currentPage = 1;
          await onSearch();
        });
      }
    });
  }

  watch(
    pwdForm,
    ({ newPwd }) =>
      (curScore.value = isAllEmpty(newPwd)
        ? -1
        : zxcvbnFactory.check(newPwd).score)
  );

  /** 重置密码（登录账号跨学校共用，修改后对该账号可进入的所有学校生效） */
  function handleReset(row: UserProfileRow) {
    addDialog({
      title: `重置「${userLabel(row)}」的密码`,
      confirmAction: "warning",
      width: "30%",
      draggable: true,
      closeOnClickModal: false,
      fullscreen: deviceDetection(),
      contentRenderer: () => (
        <>
          <ElForm ref={ruleFormRef} model={pwdForm}>
            <ElFormItem
              prop="newPwd"
              rules={[
                { required: true, message: "请输入新密码", trigger: "blur" },
                { min: 6, message: "密码至少 6 位", trigger: "blur" }
              ]}
            >
              <ElInput
                clearable
                show-password
                type="password"
                v-model={pwdForm.newPwd}
                placeholder="请输入新密码"
              />
            </ElFormItem>
          </ElForm>
          <div class="my-4 flex">
            {pwdProgress.map(({ color, text }, idx) => (
              <div
                class="w-[19vw]"
                style={{ marginLeft: idx !== 0 ? "4px" : 0 }}
              >
                <ElProgress
                  striped
                  striped-flow
                  duration={curScore.value === idx ? 6 : 0}
                  percentage={curScore.value >= idx ? 100 : 0}
                  color={color}
                  stroke-width={10}
                  show-text={false}
                />
                <p
                  class="text-center"
                  style={{ color: curScore.value === idx ? color : "" }}
                >
                  {text}
                </p>
              </div>
            ))}
          </div>
        </>
      ),
      closeCallBack: () => (pwdForm.newPwd = ""),
      beforeSure: done => {
        ruleFormRef.value.validate(async valid => {
          if (!valid) return;
          try {
            await resetUserProfilePassword(row.id, pwdForm.newPwd);
          } catch (error) {
            message(errorText(error, "密码重置失败"), { type: "error" });
            return;
          }
          message(`已重置「${userLabel(row)}」的密码`, { type: "success" });
          done();
        });
      }
    });
  }

  /** 分配角色 */
  function handleRole(row: UserProfileRow) {
    addDialog({
      title: `分配「${userLabel(row)}」的角色`,
      props: {
        formInline: {
          display_name: userLabel(row),
          roleOptions: roleOptions.value,
          ids: (row.roles ?? []).map(role => role.id)
        } satisfies RoleFormItemProps
      },
      width: "420px",
      draggable: true,
      fullscreen: deviceDetection(),
      fullscreenIcon: true,
      closeOnClickModal: false,
      contentRenderer: () => h(roleForm),
      beforeSure: async (done, { options }) => {
        const curData = options.props.formInline as RoleFormItemProps;
        try {
          await updateUserProfile(row.id, { role_ids: curData.ids });
        } catch (error) {
          message(errorText(error, "角色分配失败"), { type: "error" });
          return;
        }
        message(`已更新「${userLabel(row)}」的角色`, { type: "success" });
        done();
        await onSearch();
      }
    });
  }

  async function loadTree() {
    treeLoading.value = true;
    try {
      const [orgRes, departments] = await Promise.all([
        getOrganizationTree(),
        fetchAllDepartments()
      ]);
      const orgTree = orgRes.data ?? [];
      orgOptions.value = flattenOrgs(orgTree);
      const deptByOrg = new Map<string, OrgDeptNode[]>();
      const deptTree: any[] = handleTree(
        departments.map(dept => ({
          id: dept.id,
          parent_id: dept.parent_id,
          name: dept.department_name,
          node_type: "dept",
          org_id: dept.org_id,
          disabled: !dept.is_active
        })),
        "id",
        "parent_id"
      );
      for (const dept of deptTree) {
        const list = deptByOrg.get(dept.org_id) ?? [];
        list.push(dept);
        deptByOrg.set(dept.org_id, list);
      }
      const toNode = (org: OrganizationTreeNode): OrgDeptNode => ({
        id: org.id,
        name: org.org_name,
        node_type: "org",
        org_id: org.id,
        children: [
          ...(org.children ?? []).map(toNode),
          ...(deptByOrg.get(org.id) ?? [])
        ]
      });
      treeData.value = orgTree.map(toNode);
    } catch (error) {
      message(errorText(error, "加载组织架构失败"), { type: "error" });
    } finally {
      treeLoading.value = false;
    }
  }

  onMounted(async () => {
    onSearch();
    await loadTree();
    try {
      roleOptions.value = await fetchAllRoles({ is_active: true });
    } catch {
      roleOptions.value = [];
    }
  });

  return {
    form,
    loading,
    columns,
    dataList,
    treeData,
    treeLoading,
    selectedNum,
    pagination,
    buttonClass,
    deviceDetection,
    onSearch,
    resetForm,
    onbatchDel,
    openDialog,
    onTreeSelect,
    handleDelete,
    handleReset,
    handleRole,
    handleSizeChange,
    onSelectionCancel,
    handleCurrentChange,
    handleSelectionChange
  };
}
