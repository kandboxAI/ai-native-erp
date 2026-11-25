<template>
  <div class="list-page">
    <ReListHeading
      :data-list-key="`goods-${permission}-v2`"
      :title="title || noun"
    />
    <section class="list-query-panel">
      <div class="tab-toolbar list-filters">
        <el-form inline class="tab-filter" @submit.prevent>
          <el-form-item>
            <el-input
              v-model="keyword"
              clearable
              :placeholder="searchPlaceholder || '关键字'"
              @keyup.enter="search"
            />
          </el-form-item>
          <el-form-item v-for="f in filters || []" :key="f.prop">
            <el-select
              v-model="filterValues[f.prop]"
              clearable
              filterable
              :placeholder="f.label"
              style="width: 170px"
            >
              <el-option
                v-for="o in f.options()"
                :key="String(o.value)"
                :label="o.label"
                :value="o.value"
              />
            </el-select>
          </el-form-item>
          <el-form-item>
            <el-button data-list-query="search" type="primary" @click="search"
              >搜索</el-button
            >
            <el-button data-list-query="reset" @click="resetQuery">重置</el-button>
          </el-form-item>
        </el-form>
      </div>

      <ReListTable
        :list-heading="false"
        :list-key="`goods-${permission}-v2`"

        :list-refresh="load"
        v-loading="loading"
        :data="rows"
        row-key="id"
        class="data-table"
      >
        <el-table-column
          v-for="c in columns"
          :key="c.prop"
          :prop="c.prop"
          :label="c.label"
          :min-width="c.width || 120"
          :list-hidden="c.hidden"
          :fixed="c.type === 'identity' ? 'left' : undefined"
          show-overflow-tooltip
        >
          <template #default="{ row }">
            <ReListIdentity v-if="c.type === 'identity'" :primary="row[c.prop]" :secondary="row[c.secondaryProp || '']" />
            <template v-else-if="c.type === 'bool'">
              <el-tag :type="row[c.prop] ? 'success' : 'info'" size="small">{{
                row[c.prop] ? c.trueText || "是" : c.falseText || "否"
              }}</el-tag>
            </template>
            <template v-else>{{
              c.format ? c.format(row) : (row[c.prop] ?? "—")
            }}</template>
          </template>
        </el-table-column>
        <el-table-column label="操作" :width="actionWidth || 140" fixed="right">
          <template #default="{ row }">
            <el-button
              data-list-action="edit"
              v-if="api.update && hasPerms(`${permission}:update`)"
              link
              type="primary"
              @click="openDialog(row)"
              >编辑</el-button
            >
            <el-button
              data-list-action="delete"
              v-if="
                api.remove &&
                hasPerms(`${permission}:delete`) &&
                !(isProtected && isProtected(row))
              "
              link
              type="danger"
              @click="remove(row)"
              >删除</el-button
            >
            <slot name="actions" :row="row" />
          </template>
        </el-table-column>

        <template #list-actions
          ><div class="header-actions">
            <el-button
              data-list-action="create"
              v-if="api.create && hasPerms(`${permission}:create`)"
              type="primary"
              round
              :icon="Plus"
              @click="openDialog()"
              >新增{{ noun }}</el-button
            >
            <slot name="toolbar" /></div
        ></template>

        <template #list-pagination
          ><div class="table-footer">
            <ReListPagination
              v-model:current-page="page"
              v-model:page-size="pageSize"
              :total="total"
              @current-change="load"
              @size-change="search"
            /></div
        ></template>
      </ReListTable>
    </section>

    <el-dialog
      v-model="dialogVisible"
      :title="editing ? `编辑${noun}` : `新增${noun}`"
      width="560px"
      :append-to-body="dialogAppendToBody"
      destroy-on-close
    >
      <el-form label-width="110px">
        <template v-for="f in fields" :key="f.prop">
          <el-form-item
            v-if="!(editing && f.createOnly)"
            :label="f.label"
            :required="f.required"
          >
            <el-select
              v-if="f.type === 'select'"
              v-model="form[f.prop]"
              :clearable="!f.required"
              filterable
              style="width: 100%"
              :disabled="editing && f.readonlyOnEdit"
            >
              <el-option
                v-for="o in f.options ? f.options(form) : []"
                :key="String(o.value)"
                :label="o.label"
                :value="o.value"
              />
            </el-select>
            <WarehouseDepartmentSelect v-else-if="f.type === 'warehouse_department'" v-model="form[f.prop]"
              :placeholder="f.placeholder"
              :org-id="form.org_id || editing?.org_id" :permission-key="permission + (editing ? ':update' : ':create')" />
            <WarehouseCustodianSelect v-else-if="f.type === 'warehouse_custodian'" v-model="form[f.prop]"
              :org-id="form.org_id || editing?.org_id" :permission-key="permission + (editing ? ':update' : ':create')" />
            <LocationSelect v-else-if="f.type === 'location'" v-model="form[f.prop]"
              :selected-label="editing?.location_name || ''"
              :disabled="!form.org_id && !editing?.org_id" :org-id="form.org_id || editing?.org_id" :permission-key="permission + (editing ? ':update' : ':create')" />
            <el-switch v-else-if="f.type === 'switch'" v-model="form[f.prop]" />
            <el-input-number
              v-else-if="f.type === 'number'"
              v-model="form[f.prop]"
              :controls="false"
              style="width: 100%"
            />
            <el-input
              v-else-if="f.type === 'textarea'"
              v-model="form[f.prop]"
              type="textarea"
              :rows="3"
            />
            <el-input
              v-else
              v-model="form[f.prop]"
              :placeholder="f.placeholder"
              :disabled="editing && f.readonlyOnEdit"
            />
            <div v-if="f.hint" class="field-hint">{{ f.hint }}</div>
          </el-form-item>
        </template>
      </el-form>
      <template #footer>
        <el-button data-action="neutral" @click="dialogVisible = false">取消</el-button>
        <el-button data-action="primary" type="primary" :loading="saving" @click="save"
          >保存</el-button
        >
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import LocationSelect from "@plugins/inv/web/src/components/LocationSelect.vue";
import WarehouseDepartmentSelect from "../components/WarehouseDepartmentSelect.vue";
import WarehouseCustodianSelect from "../components/WarehouseCustodianSelect.vue";
import { onMounted, reactive, ref, watch } from "vue";
import { Plus } from "@element-plus/icons-vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { hasPerms } from "@/utils/auth";
import { getHttpErrorMessage } from "@/utils/http";

type Row = Record<string, any>;
type Option = { label: string; value: string | boolean | number };
export type CrudColumn = {
  prop: string;
  label: string;
  width?: number;
  type?: "bool" | "identity";
  secondaryProp?: string;
  hidden?: boolean;
  trueText?: string;
  falseText?: string;
  format?: (row: Row) => string;
};
export type CrudField = {
  prop: string;
  label: string;
  type?: "text" | "select" | "switch" | "number" | "textarea" | "location" | "warehouse_department" | "warehouse_custodian";
  required?: boolean;
  default?: unknown;
  placeholder?: string;
  hint?: string;
  options?: (form: Row) => Option[];
  createOnly?: boolean;
  readonlyOnEdit?: boolean;
  resetOnOrgChange?: boolean;
};
type Result<T> = Promise<{ code: number; message: string; data: T }>;
export type CrudApi = {
  list: (params: Row) => Result<{ items: Row[]; total: number }>;
  create?: (body: Row) => Result<unknown>;
  update?: (id: string, body: Row) => Result<unknown>;
  remove?: (id: string) => Result<unknown>;
};

const props = defineProps<{
  noun: string;
  title?: string;
  description?: string;
  permission: string;
  api: CrudApi;
  columns: CrudColumn[];
  fields: CrudField[];
  filters?: { prop: string; label: string; options: () => Option[] }[];
  searchPlaceholder?: string;
  actionWidth?: number;
  isProtected?: (row: Row) => boolean;
  dialogAppendToBody?: boolean;
  deleteConfirmMessage?: string;
}>();
const emit = defineEmits<{ changed: [] }>();

const loading = ref(false);
const saving = ref(false);
const rows = ref<Row[]>([]);
const total = ref(0);
const page = ref(1);
const pageSize = ref(20);
const keyword = ref("");
const filterValues = reactive<Row>({});
const dialogVisible = ref(false);
const editing = ref<Row | null>(null);
const form = reactive<Row>({});

async function load() {
  loading.value = true;
  try {
    const params: Row = {
      page: page.value,
      page_size: pageSize.value,
      keyword: keyword.value || undefined
    };
    Object.entries(filterValues).forEach(([k, v]) => {
      if (v !== "" && v !== null && v !== undefined) params[k] = v;
    });
    const res = await props.api.list(params);
    if (res.code !== 0) throw new Error(res.message);
    rows.value = res.data.items;
    total.value = res.data.total;
  } catch (err) {
    ElMessage.error(getHttpErrorMessage(err, `加载${props.noun}失败`));
  } finally {
    loading.value = false;
  }
}
function search() {
  page.value = 1;
  load();
}

function resetQuery() {
  keyword.value = "";
  Object.keys(filterValues).forEach(key => delete filterValues[key]);
  search();
}

function openDialog(row?: Row) {
  editing.value = row ?? null;
  Object.keys(form).forEach(k => delete form[k]);
  props.fields.forEach(f => {
    form[f.prop] = row
      ? (row[f.prop] ?? null)
      : (f.default ?? (f.type === "switch" ? false : null));
  });
  dialogVisible.value = true;
}

async function save() {
  const missing = props.fields.find(
    f =>
      f.required &&
      !(editing.value && f.createOnly) &&
      (form[f.prop] === null || form[f.prop] === "")
  );
  if (missing) return ElMessage.warning(`请填写${missing.label}`);
  saving.value = true;
  try {
    const body: Row = {};
    props.fields.forEach(f => {
      if (editing.value && (f.createOnly || f.readonlyOnEdit)) return;
      const value = form[f.prop];
      body[f.prop] = value === "" ? null : value;
    });
    const res = editing.value
      ? await props.api.update!(editing.value.id, body)
      : await props.api.create!(body);
    if (res.code !== 0) throw new Error(res.message);
    ElMessage.success("已保存");
    dialogVisible.value = false;
    load();
    emit("changed");
  } catch (err) {
    ElMessage.error(getHttpErrorMessage(err, "保存失败"));
  } finally {
    saving.value = false;
  }
}

async function remove(row: Row) {
  try {
    await ElMessageBox.confirm(props.deleteConfirmMessage || `确定删除该${props.noun}吗？`, "删除", {
      confirmButtonClass: "app-button-danger",
      type: "warning"
    });
  } catch {
    return;
  }
  try {
    const res = await props.api.remove!(row.id);
    if (res.code !== 0) throw new Error(res.message);
    ElMessage.success("已删除");
    load();
    emit("changed");
  } catch (err) {
    ElMessage.error(getHttpErrorMessage(err, "删除失败"));
  }
}

watch(() => form.org_id, (value, previous) => {
  if (previous && value !== previous && !editing.value) {
    props.fields.filter(field => field.type === "location" || field.resetOnOrgChange).forEach(field => form[field.prop] = null);
  }
});
onMounted(load);
defineExpose({ reload: load });
</script>

<style scoped>
.field-hint {
  width: 100%;
  margin-top: 6px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 1.5;
}
</style>
