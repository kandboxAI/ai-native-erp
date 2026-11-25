<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import ReListTable from "@/components/ReListTable";
import { useUserStoreHook } from "@/store/modules/user";
import { getHttpErrorMessage } from "@/utils/http";
import {
  fetchAllUserProfiles,
  updateUserProfile,
  type UserProfileRow
} from "@/api/systemUserProfile";
import {
  getPositionOptions,
  fetchAllPositions,
  savePosition,
  deletePosition,
  type Position,
  type PositionOptions
} from "@/api/position";

defineOptions({ name: "SystemPosition" });
const router = useRouter();
const has = (permission: string) =>
  useUserStoreHook().permissions.includes(permission);
const options = ref<PositionOptions>();
const rows = ref<Position[]>([]);
const query = reactive({ page: 1, page_size: 20, keyword: "" });
const loading = ref(false);
const saving = ref(false);
const deleting = ref(false);
const selectedRows = ref<TableRow[]>([]);
const visible = ref(false);
const users = ref<UserProfileRow[]>([]);
const usersLoaded = ref(false);
const usersLoading = ref(false);
const membersVisible = ref(false);
const memberPosition = ref<Position>();
const memberKeyword = ref("");
const onlyLinked = ref(false);
const savingUser = ref("");
const userCounts = computed(() => {
  const counts = new Map<string, number>();
  for (const user of users.value) {
    for (const id of user.position_ids)
      counts.set(id, (counts.get(id) || 0) + 1);
  }
  return counts;
});
const isLinked = (user: UserProfileRow) =>
  !!memberPosition.value && user.position_ids.includes(memberPosition.value.id);
const memberUsers = computed(() => {
  const keyword = memberKeyword.value.trim().toLowerCase();
  return users.value
    .filter(
      user =>
        user.org_id === memberPosition.value?.org_id &&
        (!onlyLinked.value || isLinked(user)) &&
        (!keyword ||
          [user.full_name, user.display_name, user.department_name].some(
            value => value?.toLowerCase().includes(keyword)
          ))
    )
    .sort((a, b) => Number(isLinked(b)) - Number(isLinked(a)));
});

async function loadUsers() {
  usersLoaded.value = false;
  usersLoading.value = true;
  try {
    users.value = await fetchAllUserProfiles();
    usersLoaded.value = true;
    return true;
  } catch (error) {
    ElMessage.error(getHttpErrorMessage(error, "关联用户加载失败"));
    return false;
  } finally {
    usersLoading.value = false;
  }
}
async function manageUsers(position: Position) {
  memberPosition.value = position;
  memberKeyword.value = "";
  onlyLinked.value = false;
  if (await loadUsers()) membersVisible.value = true;
}
async function changeUserPosition(user: UserProfileRow) {
  if (!memberPosition.value || savingUser.value) return;
  const positionId = memberPosition.value.id;
  const linked = isLinked(user);
  savingUser.value = user.id;
  try {
    // 只改当前岗位，保留该用户的其他岗位；复用用户维护的范围与岗位校验。
    const result = await updateUserProfile(user.id, {
      position_ids: linked
        ? user.position_ids.filter(id => id !== positionId)
        : [...user.position_ids, positionId]
    });
    if (result.code !== 0) throw new Error(result.message);
    users.value = users.value.map(row =>
      row.id === user.id ? result.data : row
    );
    ElMessage.success(linked ? "已移除关联" : "已关联用户");
  } catch (error) {
    ElMessage.error(getHttpErrorMessage(error, "关联用户修改失败"));
  } finally {
    savingUser.value = "";
  }
}
const emptyForm = () => ({
  id: "",
  org_id: "",
  position_no: "",
  position_name: "",
  department_id: "",
  parent_position_id: null as string | null,
  is_department_head: false,
  headcount: null as number | null,
  sort_no: null as number | null,
  is_active: true,
  updated_at: ""
});
const form = reactive(emptyForm());
const departments = computed(
  () =>
    options.value?.departments.filter(row => row.org_id === form.org_id) || []
);
const parents = computed(
  () =>
    options.value?.positions.filter(
      row => row.org_id === form.org_id && row.is_active && row.id !== form.id
    ) || []
);

type TableRow = {
  id: string;
  org_id: string;
  name: string;
  no?: string;
  department_id?: string;
  record?: Position;
  children?: TableRow[];
};
const tableRows = computed<TableRow[]>(() => {
  const keyword = query.keyword.trim().toLowerCase();
  const recordRow = (row: Position): TableRow => ({
    id: row.id,
    org_id: row.org_id,
    record: row,
    name: row.position_name,
    no: row.position_no
  });
  const groups = new Map<string, TableRow>();
  for (const department of options.value?.departments || []) {
    groups.set(department.id, {
      id: `department:${department.id}`,
      department_id: department.id,
      org_id: department.org_id,
      name: department.name,
      children: []
    });
  }
  for (const row of rows.value as Position[]) {
    if (!groups.has(row.department_id)) {
      groups.set(row.department_id, {
        id: `department:${row.department_id}`,
        org_id: row.org_id,
        name: "未归属可见部门",
        children: []
      });
    }
    groups.get(row.department_id)!.children!.push(recordRow(row));
  }
  return [...groups.values()].flatMap(department => {
    if (!keyword || department.name.toLowerCase().includes(keyword))
      return [department];
    const children = department.children!.filter(
      row =>
        row.name.toLowerCase().includes(keyword) ||
        row.no!.toLowerCase().includes(keyword)
    );
    return children.length ? [{ ...department, children }] : [];
  });
});

async function load() {
  selectedRows.value = [];
  loading.value = true;
  try {
    const [references, result] = await Promise.all([
      getPositionOptions(),
      fetchAllPositions().then(items => ({
        code: 0,
        message: "",
        data: { items }
      }))
    ]);
    if (references.code !== 0) throw new Error(references.message);
    if (result.code !== 0) throw new Error(result.message);
    options.value = references.data;
    rows.value = result.data.items;
    if (has("user_profile:list")) await loadUsers();
  } catch (error) {
    ElMessage.error(getHttpErrorMessage(error, "岗位配置加载失败"));
  } finally {
    loading.value = false;
  }
}
async function search() {
  query.page = 1;
  await load();
}
function selectRows(selection: TableRow[]) {
  selectedRows.value = selection.filter(row => row.record);
}
async function remove(records: Position[]) {
  if (!records.length || deleting.value) return;
  const label = "岗位";
  let deleted = 0;
  let attempted = false;
  deleting.value = true;
  try {
    await ElMessageBox.confirm(
      `将删除选中的 ${records.length} 个${label}；关联知识库及全部文档可能随之删除，无法恢复。是否继续？`,
      "确认删除",
      {
        type: "warning",
        confirmButtonText: "确认删除",
        cancelButtonText: "取消"
      }
    );
    attempted = true;
    // 逐项复用现有删除校验，失败即停止，避免继续扩大删除范围。
    for (const row of records) {
      const result = await deletePosition(row.id);
      if (result.code !== 0) throw new Error(result.message);
      deleted += 1;
    }
    ElMessage.success(`已删除 ${deleted} 个${label}`);
  } catch (error) {
    if (error !== "cancel" && error !== "close")
      ElMessage.error(
        `已删除 ${deleted}/${records.length} 个${label}，已停止：${getHttpErrorMessage(error, "删除失败")}`
      );
  } finally {
    if (attempted) await load();
    deleting.value = false;
  }
}
function edit(row?: Position, department?: TableRow) {
  Object.assign(
    form,
    emptyForm(),
    {
      org_id: department?.org_id || options.value?.organizations[0]?.id || "",
      department_id: department?.department_id || ""
    },
    row || {}
  );
  visible.value = true;
}
async function save() {
  if (
    !form.org_id ||
    !form.position_no.trim() ||
    !form.position_name.trim() ||
    !form.department_id
  ) {
    ElMessage.warning("请填写组织、部门、岗位编号和名称");
    return;
  }
  const data = {
    org_id: form.org_id,
    position_no: form.position_no,
    position_name: form.position_name,
    department_id: form.department_id,
    parent_position_id: form.parent_position_id,
    is_department_head: form.is_department_head,
    headcount: form.headcount,
    sort_no: form.sort_no,
    is_active: form.is_active
  };
  saving.value = true;
  try {
    const result = await savePosition(form.id || undefined, {
      ...data,
      ...(form.id ? { updated_at: form.updated_at } : {})
    });
    if (result.code !== 0) throw new Error(result.message);
    visible.value = false;
    ElMessage.success("已保存");
    await load();
  } catch (error) {
    ElMessage.error(getHttpErrorMessage(error, "岗位保存失败"));
  } finally {
    saving.value = false;
  }
}
function configureKnowledge(positionId: string) {
  router.push({
    name: "KnowledgePositions",
    query: { position_id: positionId }
  });
}
onMounted(load);
</script>

<template>
  <ReListPresentation>
    <div class="main list-page list-presentation-container">
      <ReListHeading title="岗位管理" />
      <section class="list-query-panel">
        <el-form class="list-filters" inline @submit.prevent="search">
          <el-form-item label="名称或编号"
            ><el-input v-model="query.keyword" clearable @keyup.enter="search"
          /></el-form-item>
          <el-form-item
            ><el-button
              type="primary"
              data-list-query="search"
              :loading="loading"
              @click="search"
              >查询</el-button
            ><el-button
              data-list-query="reset"
              @click="
                query.keyword = '';
                search();
              "
              >重置</el-button
            ></el-form-item
          >
        </el-form>
        <ReListTable
          v-loading="loading || deleting"
          :data="tableRows"
          default-expand-all
          row-key="id"
          :list-refresh="load"
          :list-heading="false"
          list-key="position"
          list-title="岗位"
          @selection-change="selectRows"
        >
          <template #list-actions>
            <el-button
              v-if="has('position:create')"
              type="primary"
              data-list-action="create"
              @click="edit()"
            >
              新增岗位
            </el-button>
            <el-button
              v-if="has('position:delete')"
              type="danger"
              data-list-action="delete"
              :disabled="loading || !selectedRows.length"
              :loading="deleting"
              @click="remove(selectedRows.map(row => row.record!))"
            >
              批量删除（{{ selectedRows.length }}）
            </el-button>
          </template>
          <el-table-column
            v-if="has('position:delete')"
            type="selection"
            width="48"
            :selectable="(row: TableRow) => !!row.record"
          />
          <el-table-column prop="name" label="部门 / 岗位" min-width="220" />
          <el-table-column prop="no" label="编号" min-width="120" />
          <el-table-column
            v-if="has('user_profile:list')"
            label="关联用户"
            width="120"
          >
            <template #default="{ row }">
              <el-button
                v-if="row.record"
                link
                type="primary"
                :disabled="usersLoading || !usersLoaded"
                @click="manageUsers(row.record)"
              >
                {{ usersLoaded ? userCounts.get(row.id) || 0 : "—" }} 人
              </el-button>
              <span v-else>—</span>
            </template>
          </el-table-column>
          <el-table-column label="状态"
            ><template #default="{ row }">{{
              row.record ? (row.record.is_active ? "启用" : "停用") : "—"
            }}</template></el-table-column
          >
          <el-table-column label="操作"
            ><template #default="{ row }">
              <el-button
                v-if="row.department_id && has('position:create')"
                link
                type="primary"
                data-list-action="create"
                @click="edit(undefined, row as TableRow)"
                >新增岗位</el-button
              >
              <el-button
                v-if="row.record && has('position:update')"
                link
                data-list-action="edit"
                type="primary"
                @click="edit(row.record)"
                >编辑</el-button
              >
              <el-button
                v-if="row.record && has('user_profile:list')"
                link
                type="primary"
                :disabled="usersLoading"
                @click="manageUsers(row.record)"
                >关联用户</el-button
              >
              <el-button
                v-if="
                  row.record &&
                  has('knowledge:authorization:manage') &&
                  router.hasRoute('KnowledgePositions')
                "
                link
                data-list-action="edit"
                type="primary"
                @click="configureKnowledge(row.id)"
                >岗位知识配置</el-button
              >
              <el-button
                v-if="row.record && has('position:delete')"
                link
                type="danger"
                data-list-action="delete"
                :disabled="deleting"
                @click="remove([row.record])"
                >删除</el-button
              >
            </template></el-table-column
          >
        </ReListTable>
      </section>

      <el-dialog
        v-model="membersVisible"
        :title="`${memberPosition?.position_name || ''} · 关联用户`"
        width="760px"
        :close-on-click-modal="false"
        :show-close="!savingUser"
        :close-on-press-escape="!savingUser"
      >
        <el-form class="erp-query-form" inline @submit.prevent>
          <el-form-item label="用户 / 部门">
            <el-input
              v-model="memberKeyword"
              clearable
              placeholder="输入姓名或部门"
            />
          </el-form-item>
          <el-form-item
            ><el-checkbox v-model="onlyLinked"
              >仅看已关联</el-checkbox
            ></el-form-item
          >
        </el-form>
        <el-table :data="memberUsers" max-height="420" row-key="id">
          <el-table-column label="用户" min-width="150">
            <template #default="{ row }">{{
              row.full_name || row.display_name
            }}</template>
          </el-table-column>
          <el-table-column
            prop="department_name"
            label="部门"
            min-width="140"
          />
          <el-table-column label="状态" width="80">
            <template #default="{ row }">{{
              row.is_active && row.account_is_active ? "启用" : "停用"
            }}</template>
          </el-table-column>
          <el-table-column label="关联状态" width="100">
            <template #default="{ row }">{{
              isLinked(row as UserProfileRow) ? "已关联" : "未关联"
            }}</template>
          </el-table-column>
          <el-table-column
            v-if="has('user_profile:update')"
            label="操作"
            width="100"
          >
            <template #default="{ row }">
              <el-button
                link
                :type="isLinked(row as UserProfileRow) ? 'danger' : 'primary'"
                :loading="savingUser === row.id"
                :disabled="
                  !!savingUser ||
                  (!isLinked(row as UserProfileRow) &&
                    (!memberPosition?.is_active ||
                      !row.is_active ||
                      !row.account_is_active))
                "
                @click="changeUserPosition(row as UserProfileRow)"
                >{{
                  isLinked(row as UserProfileRow) ? "移除" : "关联"
                }}</el-button
              >
            </template>
          </el-table-column>
        </el-table>
        <template #footer>
          <el-button :disabled="!!savingUser" @click="membersVisible = false"
            >关闭</el-button
          >
        </template>
      </el-dialog>

      <el-dialog
        v-model="visible"
        :title="`${form.id ? '编辑' : '新增'}岗位`"
        width="580px"
        :close-on-click-modal="false"
      >
        <el-form label-width="100px" :disabled="saving">
          <el-form-item label="所属组织" required
            ><el-select
              v-model="form.org_id"
              :disabled="!!form.id"
              @change="
                form.department_id = '';
                form.parent_position_id = null;
              "
              ><el-option
                v-for="row in options?.organizations"
                :key="row.id"
                :label="row.name"
                :value="row.id" /></el-select
          ></el-form-item>
          <el-form-item label="岗位编号" required
            ><el-input v-model="form.position_no" maxlength="64"
          /></el-form-item>
          <el-form-item label="岗位名称" required
            ><el-input v-model="form.position_name" maxlength="128"
          /></el-form-item>
          <el-form-item label="所属部门" required
            ><el-select v-model="form.department_id" :disabled="!!form.id"
              ><el-option
                v-for="row in departments"
                :key="row.id"
                :label="row.name"
                :value="row.id" /></el-select
          ></el-form-item>
          <el-collapse>
            <el-collapse-item title="更多设置" name="advanced">
              <el-form-item label="上级岗位"
                ><el-select
                  v-model="form.parent_position_id"
                  clearable
                  filterable
                  @clear="form.parent_position_id = null"
                  ><el-option
                    v-for="row in parents"
                    :key="row.id"
                    :label="row.name"
                    :value="row.id" /></el-select
              ></el-form-item>
              <el-form-item label="部门负责人"
                ><el-switch v-model="form.is_department_head"
              /></el-form-item>
              <el-form-item label="编制人数"
                ><el-input-number
                  v-model="form.headcount"
                  :min="1"
                  :value-on-clear="null"
                  placeholder="留空不限"
              /></el-form-item>
            </el-collapse-item>
          </el-collapse>
          <el-form-item label="启用"
            ><el-switch v-model="form.is_active"
          /></el-form-item>
        </el-form>
        <template #footer
          ><el-button :disabled="saving" @click="visible = false"
            >取消</el-button
          ><el-button type="primary" :loading="saving" @click="save"
            >保存</el-button
          ></template
        >
      </el-dialog>
    </div>
  </ReListPresentation>
</template>

<style scoped>
.el-pagination {
  margin-top: 16px;
  justify-content: flex-end;
}
</style>
