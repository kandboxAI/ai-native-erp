import editForm from "../form.vue";
import orgForm from "../form-org.vue";
import { handleTree } from "@/utils/tree";
import { message } from "@/utils/message";
import { hasPerms } from "@/utils/auth";
import {
  createDepartment,
  createOrganization,
  deleteDepartment,
  deleteOrganization,
  fetchAllDepartments,
  getOrganization,
  getOrganizationTree,
  updateDepartment,
  updateOrganization,
  type DepartmentPayload,
  type DepartmentRow,
  type OrganizationPayload
} from "@/api/system";
import type { OrganizationTreeNode } from "@/api/organizationStructure";
import { fetchAllUserProfiles } from "@/api/systemUserProfile";
import { usePublicHooks } from "../../hooks";
import { addDialog } from "@/components/ReDialog";
import { computed, h, onMounted, reactive, ref } from "vue";
import { ElMessageBox } from "element-plus";
import type {
  DeptOption,
  FormItemProps,
  OrgFormItemProps,
  OrgOption,
  StructureRow
} from "../utils/types";
import { cloneDeep, deviceDetection } from "@pureadmin/utils";

const TYPE_LABEL: Record<string, string> = {
  group: "集团",
  school: "学校",
  organization: "组织",
  department: "部门"
};

function flattenOrgs(
  nodes: OrganizationTreeNode[],
  school?: OrganizationTreeNode
): OrgOption[] {
  return nodes.flatMap(node => {
    const owner = node.org_type_code === "school" ? node : school;
    return [
      {
        id: node.id,
        org_name: node.org_name,
        org_type_code: node.org_type_code,
        school_id: owner?.id ?? "",
        school_name: owner?.org_name ?? "",
        is_active: node.is_active
      },
      ...flattenOrgs(node.children ?? [], owner)
    ];
  });
}

function errorText(error: unknown, fallback: string) {
  const anyError = error as {
    response?: { data?: { message?: string; detail?: string } };
    message?: string;
  };
  return (
    anyError?.response?.data?.message ||
    anyError?.response?.data?.detail ||
    anyError?.message ||
    fallback
  );
}

function placementLabel(org: OrgOption | undefined) {
  if (!org) return "";
  if (org.school_name && org.org_name !== org.school_name) {
    return `${org.school_name} / ${org.org_name}`;
  }
  return org.org_name;
}

export function useDept() {
  const form = reactive({
    school_id: "",
    keyword: "",
    type_code: "",
    is_active: null as boolean | null
  });

  const formRef = ref();
  const orgFormRef = ref();
  const dataList = ref<StructureRow[]>([]);
  const fullTree = ref<StructureRow[]>([]);
  const orgOptions = ref<OrgOption[]>([]);
  const schoolOptions = computed(() =>
    orgOptions.value.filter(org => org.org_type_code === "school")
  );
  const managerOptions = ref<Array<{ id: string; label: string }>>([]);
  const loading = ref(true);
  const switchLoadMap = ref<Record<string, { loading: boolean }>>({});
  const { switchStyle } = usePublicHooks();
  const canOrgCreate = computed(() => hasPerms("organization:create"));
  const canOrgUpdate = computed(() => hasPerms("organization:update"));
  const canOrgDelete = computed(() => hasPerms("organization:delete"));
  const canDeptCreate = computed(() => hasPerms("department:create"));
  const canDeptUpdate = computed(() => hasPerms("department:update"));
  const canDeptDelete = computed(() => hasPerms("department:delete"));

  const columns: TableColumnList = [
    { label: "名称", prop: "name", width: 220, align: "left" },
    { label: "类型", prop: "type_label", minWidth: 80 },
    { label: "编号", prop: "code", minWidth: 120 },
    { label: "所属学校", prop: "school_name", minWidth: 140 },
    { label: "负责人", prop: "manager_name", minWidth: 100 },
    { label: "排序", prop: "sort_no", minWidth: 70 },
    {
      label: "状态",
      minWidth: 100,
      cellRenderer: scope => {
        const row = scope.row as StructureRow;
        const allowed =
          row.kind === "org" ? canOrgUpdate.value : canDeptUpdate.value;
        if (!allowed) return <span>{row.is_active ? "启用" : "停用"}</span>;
        return (
          <el-switch
            size={scope.props.size === "small" ? "small" : "default"}
            loading={switchLoadMap.value[row.id]?.loading}
            v-model={row.is_active}
            active-text="启用"
            inactive-text="停用"
            inline-prompt
            style={switchStyle.value}
            onChange={() => onStatusChange(row)}
          />
        );
      }
    },
    { label: "备注", prop: "remark", minWidth: 160 },
    { label: "操作", fixed: "right", width: 320, slot: "operation" }
  ];

  function onStatusChange(row: StructureRow) {
    const allowed =
      row.kind === "org" ? canOrgUpdate.value : canDeptUpdate.value;
    if (!allowed) {
      row.is_active = !row.is_active;
      return;
    }
    ElMessageBox.confirm(
      `确认要<strong>${row.is_active ? "启用" : "停用"}</strong><strong style='color:var(--el-color-primary)'>${row.name}</strong>吗?`,
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
          if (row.kind === "org") {
            await updateOrganization(row.id, { is_active: row.is_active });
          } else {
            await updateDepartment(row.id, { is_active: row.is_active });
          }
          const source = findNode(fullTree.value, row.id);
          if (source) source.is_active = row.is_active;
          message("状态修改成功", { type: "success" });
        } catch (error) {
          row.is_active = !row.is_active;
          message(errorText(error, "状态修改失败"), { type: "error" });
        } finally {
          switchLoadMap.value[row.id] = { loading: false };
        }
      })
      .catch(() => {
        row.is_active = !row.is_active;
      });
  }

  function resetForm(formEl) {
    if (!formEl) return;
    formEl.resetFields();
    applyFilter();
  }

  async function loadOptions() {
    try {
      const res = await getOrganizationTree();
      orgOptions.value = flattenOrgs(res.data ?? []);
      return res.data ?? [];
    } catch {
      orgOptions.value = [];
      return [] as OrganizationTreeNode[];
    }
  }

  function deptNodes(
    departments: DepartmentRow[],
    orgMap: Map<string, OrgOption>,
    managerName: Map<string, string>
  ) {
    const byOrg = new Map<string, StructureRow[]>();
    const grouped = new Map<string, DepartmentRow[]>();
    for (const row of departments) {
      const list = grouped.get(row.org_id) ?? [];
      list.push(row);
      grouped.set(row.org_id, list);
    }
    for (const [orgId, rows] of grouped) {
      const org = orgMap.get(orgId);
      const tree = handleTree(cloneDeep(rows), "id", "parent_id");
      const mapNode = (node: DepartmentRow & { children?: DepartmentRow[] }): StructureRow => ({
        id: node.id,
        kind: "department",
        name: node.department_name,
        code: node.department_no,
        type_code: "department",
        type_label: "部门",
        is_active: node.is_active,
        sort_no: node.sort_no,
        remark: node.remark ?? "",
        org_id: node.org_id,
        parent_id: node.parent_id,
        school_name: org?.school_name || org?.org_name || "",
        manager_user_id: node.manager_user_id,
        manager_name: node.manager_user_id
          ? (managerName.get(node.manager_user_id) ?? "")
          : "",
        children: (node.children ?? []).length
          ? (node.children ?? []).map(mapNode)
          : undefined
      });
      byOrg.set(orgId, tree.map(mapNode));
    }
    return byOrg;
  }

  function buildTree(
    nodes: OrganizationTreeNode[],
    deptByOrg: Map<string, StructureRow[]>,
    orgMap: Map<string, OrgOption>
  ): StructureRow[] {
    return nodes.map(node => {
      const org = orgMap.get(node.id);
      const childOrgs = buildTree(node.children ?? [], deptByOrg, orgMap);
      const children = [...childOrgs, ...(deptByOrg.get(node.id) ?? [])];
      return {
        id: node.id,
        kind: "org" as const,
        name: node.org_name,
        code: node.org_no,
        type_code: node.org_type_code || "",
        type_label: TYPE_LABEL[node.org_type_code || ""] || "组织",
        is_active: node.is_active,
        sort_no: node.sort_no,
        remark: "",
        org_id: node.id,
        parent_id: node.parent_id,
        school_name:
          node.org_type_code === "school"
            ? node.org_name
            : org?.school_name || "",
        manager_user_id: null,
        manager_name: "",
        children: children.length ? children : undefined
      };
    });
  }

  function prune(
    nodes: StructureRow[],
    match: (row: StructureRow) => boolean
  ): StructureRow[] {
    const result: StructureRow[] = [];
    for (const node of nodes) {
      const children = prune(node.children ?? [], match);
      if (match(node) || children.length) {
        result.push({
          ...node,
          children: children.length ? children : undefined
        });
      }
    }
    return result;
  }

  function findNode(nodes: StructureRow[], id: string): StructureRow | null {
    for (const node of nodes) {
      if (node.id === id) return node;
      const found = findNode(node.children ?? [], id);
      if (found) return found;
    }
    return null;
  }

  function applyFilter() {
    let nodes = fullTree.value;
    if (form.school_id) {
      const school = findNode(nodes, form.school_id);
      nodes = school ? [school] : [];
    }
    const keyword = form.keyword.trim();
    const typeCode = form.type_code;
    const active = form.is_active;
    if (!keyword && !typeCode && (active === null || active === undefined)) {
      dataList.value = nodes;
      return;
    }
    dataList.value = prune(nodes, row => {
      if (typeCode && row.type_code !== typeCode) return false;
      if (active !== null && active !== undefined && row.is_active !== active) {
        return false;
      }
      if (keyword && !row.name.includes(keyword) && !row.code.includes(keyword)) {
        return false;
      }
      return true;
    });
  }

  async function onSearch() {
    loading.value = true;
    try {
      const orgTree = await loadOptions();
      const orgMap = new Map(orgOptions.value.map(org => [org.id, org]));
      let users: Array<{ id: string; label: string }> = [];
      try {
        const profiles = await fetchAllUserProfiles({ is_active: true });
        users = profiles.map(user => ({
          id: user.id,
          label: user.full_name || user.display_name
        }));
      } catch {
        users = [];
      }
      managerOptions.value = users;
      const managerName = new Map(users.map(user => [user.id, user.label]));
      const departments = await fetchAllDepartments();
      const deptByOrg = deptNodes(departments, orgMap, managerName);
      const orphans = departments.filter(row => !orgMap.has(row.org_id));
      fullTree.value = buildTree(orgTree, deptByOrg, orgMap);
      if (orphans.length) {
        const orphanNodes = deptNodes(orphans, orgMap, managerName);
        for (const nodes of orphanNodes.values()) fullTree.value.push(...nodes);
      }
      applyFilter();
    } catch (error) {
      message(errorText(error, "加载组织架构失败"), { type: "error" });
    } finally {
      loading.value = false;
    }
  }

  function higherDeptOptions(orgId: string): DeptOption[] {
    const orgNode = findNode(fullTree.value, orgId);
    const departments = (orgNode?.children ?? []).filter(
      child => child.kind === "department"
    );
    const mapNode = (node: StructureRow): DeptOption => ({
      id: node.id,
      department_name: node.name,
      disabled: !node.is_active,
      children: (node.children ?? []).map(mapNode)
    });
    return departments.map(mapNode);
  }

  function openDeptDialog(
    title = "新增",
    row?: Partial<StructureRow> & { org_id?: string }
  ) {
    const orgId = row?.org_id || "";
    const org = orgOptions.value.find(item => item.id === orgId);
    const editing = title === "修改";
    addDialog({
      title: `${title}部门`,
      props: {
        formInline: {
          id: editing ? row?.id : undefined,
          org_id: orgId,
          placement_label: placementLabel(org),
          department_no: editing ? (row?.code ?? "") : "",
          department_name: editing ? (row?.name ?? "") : "",
          parent_id: row?.parent_id ?? null,
          manager_user_id: editing ? (row?.manager_user_id ?? null) : null,
          sort_no: editing ? (row?.sort_no ?? 0) : 0,
          is_active: editing ? (row?.is_active ?? true) : true,
          remark: editing ? (row?.remark ?? "") : "",
          higherDeptOptions: higherDeptOptions(orgId),
          managerOptions: managerOptions.value
        } satisfies FormItemProps
      },
      width: "46%",
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
          const payload: DepartmentPayload = {
            org_id: curData.org_id,
            department_no: curData.department_no.trim(),
            department_name: curData.department_name.trim(),
            parent_id: curData.parent_id || null,
            manager_user_id: curData.manager_user_id || null,
            sort_no: curData.sort_no,
            is_active: curData.is_active,
            remark: curData.remark || null
          };
          try {
            if (curData.id) await updateDepartment(curData.id, payload);
            else await createDepartment(payload);
            message(`已${title}部门「${payload.department_name}」`, {
              type: "success"
            });
            done();
            await onSearch();
          } catch (error) {
            message(errorText(error, `${title}部门失败`), { type: "error" });
          }
        });
      }
    });
  }

  async function openOrgDialog(
    title: string,
    preset: { id?: string; parent_id?: string | null; org_type_code: string }
  ) {
    const editing = title === "修改" && Boolean(preset.id);
    let current: Partial<OrganizationPayload> = {
      org_no: "",
      org_name: "",
      org_type_code: preset.org_type_code,
      sort_no: 0,
      is_active: true,
      remark: ""
    };
    if (editing && preset.id) {
      try {
        const res = await getOrganization(preset.id);
        current = res.data ?? current;
      } catch (error) {
        message(errorText(error, "加载组织失败"), { type: "error" });
        return;
      }
    }
    const parent = orgOptions.value.find(item => item.id === preset.parent_id);
    addDialog({
      title: `${title}${TYPE_LABEL[preset.org_type_code] || "组织"}`,
      props: {
        formInline: {
          id: editing ? preset.id : undefined,
          org_no: current.org_no ?? "",
          org_name: current.org_name ?? "",
          org_type_code: preset.org_type_code,
          parent_label: parent?.org_name ?? "",
          contact_name: current.contact_name ?? "",
          contact_phone: current.contact_phone ?? "",
          province: current.province ?? "",
          city: current.city ?? "",
          district: current.district ?? "",
          address: current.address ?? "",
          sort_no: current.sort_no ?? 0,
          is_active: current.is_active ?? true,
          remark: current.remark ?? ""
        } satisfies OrgFormItemProps
      },
      width: "52%",
      draggable: true,
      fullscreen: deviceDetection(),
      fullscreenIcon: true,
      closeOnClickModal: false,
      contentRenderer: () => h(orgForm, { ref: orgFormRef, formInline: null }),
      beforeSure: (done, { options }) => {
        const FormRef = orgFormRef.value.getRef();
        const curData = options.props.formInline as OrgFormItemProps;
        FormRef.validate(async valid => {
          if (!valid) return;
          const payload: OrganizationPayload = {
            org_no: curData.org_no.trim(),
            org_name: curData.org_name.trim(),
            org_type_code: curData.org_type_code,
            parent_id: editing ? undefined : preset.parent_id || null,
            contact_name: curData.contact_name.trim() || null,
            contact_phone: curData.contact_phone.trim() || null,
            province: curData.province.trim() || null,
            city: curData.city.trim() || null,
            district: curData.district.trim() || null,
            address: curData.address.trim() || null,
            sort_no: curData.sort_no,
            is_active: curData.is_active,
            remark: curData.remark.trim() || null
          };
          if (editing) delete payload.parent_id;
          try {
            if (curData.id) await updateOrganization(curData.id, payload);
            else await createOrganization(payload);
            message(`已${title}${TYPE_LABEL[payload.org_type_code]}「${payload.org_name}」`, {
              type: "success"
            });
            done();
            await onSearch();
          } catch (error) {
            message(errorText(error, `${title}组织失败`), { type: "error" });
          }
        });
      }
    });
  }

  async function handleDelete(row: StructureRow) {
    try {
      if (row.kind === "org") await deleteOrganization(row.id);
      else await deleteDepartment(row.id);
      message(`已删除${row.type_label}「${row.name}」`, { type: "success" });
      await onSearch();
    } catch (error) {
      message(errorText(error, "删除失败"), { type: "error" });
    }
  }

  const toolbarSchoolParentId = computed(() => {
    const root = fullTree.value[0];
    if (root?.type_code === "group") return root.id;
    return "";
  });

  onMounted(() => {
    onSearch();
  });

  return {
    form,
    loading,
    columns,
    dataList,
    schoolOptions,
    canOrgCreate,
    canOrgUpdate,
    canOrgDelete,
    canDeptCreate,
    canDeptUpdate,
    canDeptDelete,
    toolbarSchoolParentId,
    onSearch,
    resetForm,
    applyFilter,
    openDeptDialog,
    openOrgDialog,
    handleDelete,
    TYPE_LABEL
  };
}
