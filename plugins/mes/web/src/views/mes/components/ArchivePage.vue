<script setup lang="ts">
import ListPagination from "@/components/ListPagination/index.vue";
import { computed, onMounted, reactive, ref } from "vue";
import { hasPerms } from "@/utils/auth";
import { getHttpErrorMessage } from "@/utils/http";
import { message, actionMessage } from "@/utils/message";
import {
  getArchives,
  saveArchive,
  archivePermission,
  archiveOrganizations,
  archiveOptions,
  type ArchiveKind,
  type ArchiveRecord,
  type ArchiveOption,
} from "@plugins/mes/web/src/api/mesArchives";
import RemoteSelect from "./RemoteSelect.vue";

const props = defineProps<{ kind: ArchiveKind; title: string }>();
const rows = ref<ArchiveRecord[]>([]),
  total = ref(0),
  page = ref(1),
  keyword = ref(""),
  state = ref<boolean>();
const loading = ref(false),
  saving = ref(false),
  visible = ref(false),
  error = ref("");
const editing = ref<ArchiveRecord>();
const previousOptions = ref<ArchiveOption[]>([]),
  previousLoading = ref(false);
const empty = () => ({
  org_id: "",
  record_no: "",
  record_name: "",
  description: "",
  sort_no: 0,
  is_active: true,
  reconciliation_mode_code: "by_item",
  pricing_description: "",
  project_stage_id: "",
  requirement_id: "",
  process_id: "",
  process_ids: [] as string[],
  processing_type_code: "in_house",
  work_center_name: "",
  is_piecework: false,
  is_quality_required: false,
  is_equipment_required: null as boolean | null,
  execution_kind_code: null as string | null,
  previous_process_ids: [] as string[],
});
const form = reactive(empty());
const canManage = computed(() => hasPerms(archivePermission(props.kind)));
let request = 0,
  previousRequest = 0;
const processingLabels: Record<string, string> = {
  in_house: "自制",
  outsourced: "委外",
  purchased: "采购",
};
async function load() {
  const current = ++request;
  loading.value = true;
  error.value = "";
  try {
    const { data } = await getArchives(props.kind, {
      keyword: keyword.value,
      is_active: state.value,
      page: page.value,
      page_size: 20,
    });
    if (current === request) {
      rows.value = data.items;
      total.value = data.total;
    }
  } catch (cause) {
    if (current === request)
      error.value = getHttpErrorMessage(cause, "档案读取失败");
  } finally {
    if (current === request) loading.value = false;
  }
}
function search() {
  page.value = 1;
  load();
}
function edit(row?: ArchiveRecord) {
  editing.value = row;
  Object.assign(form, empty(), row || {});
  form.previous_process_ids = [...(row?.previous_process_ids || [])];
  form.process_ids = [
    ...(row?.process_ids || (row?.process_id ? [row.process_id] : [])),
  ];
  previousOptions.value = (
    props.kind === "equipment" ? form.process_ids : form.previous_process_ids
  ).map((value) => ({
    value,
    label:
      row?.process_labels?.[value] ||
      row?.previous_process_labels?.[value] ||
      value,
    record_no: "",
    record_name: "",
  }));
  visible.value = true;
  if (row && ["processes", "equipment"].includes(props.kind)) searchPrevious();
}
function changedOrganization() {
  Object.assign(form, {
    project_stage_id: "",
    requirement_id: "",
    process_id: "",
    process_ids: [],
    previous_process_ids: [],
  });
  previousOptions.value = [];
  ++previousRequest;
}
async function searchPrevious(value = "") {
  if (!form.org_id) return;
  const current = ++previousRequest;
  previousLoading.value = true;
  try {
    const options = (
      await archiveOptions("processes", form.org_id, value)
    ).filter(
      (row) => props.kind !== "processes" || row.value !== editing.value?.id,
    );
    if (current === previousRequest) {
      previousOptions.value = [
        ...previousOptions.value.filter(
          (row) =>
            (props.kind === "equipment"
              ? form.process_ids
              : form.previous_process_ids
            ).includes(row.value) &&
            !options.some((option) => option.value === row.value),
        ),
        ...options,
      ];
    }
  } catch (cause) {
    if (current === previousRequest)
      actionMessage(getHttpErrorMessage(cause));
  } finally {
    if (current === previousRequest) previousLoading.value = false;
  }
}
function initialReference(key: "process" | "project_stage" | "requirement") {
  const row = editing.value;
  const value = row?.[`${key}_id`];
  return value
    ? { value, label: row?.[`${key}_label`] || "已关联档案" }
    : undefined;
}
async function save() {
  if (saving.value) return;
  if (!form.org_id || !form.record_no.trim() || !form.record_name.trim()) {
    actionMessage("请填写组织、编号和名称", "warning");
    return;
  }
  saving.value = true;
  const data: Record<string, unknown> = {
    org_id: form.org_id,
    record_no: form.record_no.trim(),
    record_name: form.record_name.trim(),
    description: form.description || null,
    sort_no: form.sort_no,
    is_active: form.is_active,
    ...(editing.value ? { version_no: editing.value.version_no } : {}),
  };
  if (props.kind === "customers")
    data.reconciliation_mode_code = form.reconciliation_mode_code;
  if (props.kind === "requirements")
    data.pricing_description = form.pricing_description || null;
  if (props.kind === "processes")
    Object.assign(data, {
      project_stage_id: form.project_stage_id || null,
      requirement_id: form.requirement_id || null,
      processing_type_code: form.processing_type_code,
      is_piecework: form.is_piecework,
      is_quality_required: form.is_quality_required,
      is_equipment_required: form.is_equipment_required,
      execution_kind_code: form.execution_kind_code || null,
      previous_process_ids: form.previous_process_ids,
    });
  if (props.kind === "equipment")
    Object.assign(data, {
      process_ids: form.process_ids,
      work_center_name: form.work_center_name || null,
    });
  try {
    await saveArchive(props.kind, editing.value?.id, data);
    visible.value = false;
    message("档案已保存", { type: "success" });
    await load();
  } catch (cause) {
    actionMessage(getHttpErrorMessage(cause, "保存失败"));
  } finally {
    saving.value = false;
  }
}
onMounted(load);
</script>
<template>
  <div class="sys-page sys-module">
    <el-card shadow="never">
      <template #header
        ><div class="archive-header">
          <h2>{{ title }}</h2>
          <el-button v-if="canManage" type="primary" @click="edit()"
            >新增{{ title }}</el-button
          >
        </div></template
      >
      <el-form inline @submit.prevent="search"
        ><el-form-item
          ><el-input
            v-model="keyword"
            placeholder="编号 / 名称"
            clearable
            @keyup.enter="search" /></el-form-item
        ><el-form-item
          ><el-select
            v-model="state"
            placeholder="全部状态"
            clearable
            style="width: 130px"
            ><el-option label="启用" :value="true" /><el-option
              label="停用"
              :value="false" /></el-select></el-form-item
        ><el-form-item
          ><el-button type="primary" @click="search">查询</el-button
          ><el-button
            @click="
              keyword = '';
              state = undefined;
              search();
            "
            >重置</el-button
          ></el-form-item
        ></el-form
      >
      <el-alert v-if="error" :title="error" type="error" :closable="false" />
      <el-table v-loading="loading" :data="rows" row-key="id">
        <el-table-column
          prop="record_no"
          label="编号"
          min-width="140"
        /><el-table-column prop="record_name" label="名称" min-width="170" />
        <el-table-column
          v-if="kind === 'processes'"
          label="加工类型"
          width="100"
          ><template #default="{ row }">{{
            processingLabels[row.processing_type_code]
          }}</template></el-table-column
        >
        <el-table-column
          v-if="kind === 'processes'"
          prop="project_stage_label"
          label="项目阶段"
          min-width="130"
        />
        <el-table-column
          v-if="kind === 'equipment'"
          prop="process_label"
          label="所属工艺"
          min-width="130"
        />
        <el-table-column
          v-if="kind === 'requirements'"
          prop="pricing_description"
          label="定价标准说明"
          min-width="180"
          show-overflow-tooltip
        />
        <el-table-column
          prop="sort_no"
          label="顺序"
          width="80"
        /><el-table-column
          prop="description"
          label="说明"
          min-width="220"
          show-overflow-tooltip
        />
        <el-table-column label="状态" width="90"
          ><template #default="{ row }"
            ><el-tag :type="row.is_active ? 'success' : 'info'">{{
              row.is_active ? "启用" : "停用"
            }}</el-tag></template
          ></el-table-column
        >
        <el-table-column v-if="canManage" label="操作" width="90"
          ><template #default="{ row }"
            ><el-button link type="primary" @click="edit(row as ArchiveRecord)"
              >编辑</el-button
            ></template
          ></el-table-column
        >
      </el-table>
      <ListPagination
        v-model:current-page="page"
        :page-size="20"
        :total="total"
        layout="total, prev, pager, next"
        @current-change="load"
      />
    </el-card>
    <el-dialog
      v-model="visible"
      :title="`${editing ? '编辑' : '新增'}${title}`"
      width="680px"
      :close-on-click-modal="false"
      destroy-on-close
    >
      <el-form label-width="110px" @submit.prevent="save">
        <el-form-item label="所属组织" required
          ><RemoteSelect
            v-model="form.org_id"
            :load-options="(value) => archiveOrganizations(kind, value)"
            :disabled="!!editing"
            :auto-select-single="true"
            :initial-option="
              editing ? { value: editing.org_id, label: '所属组织' } : undefined
            "
            placeholder="选择组织"
            @select="changedOrganization"
        /></el-form-item>
        <el-form-item label="编号" required
          ><el-input
            v-model="form.record_no"
            :disabled="!!editing"
            :maxlength="64" /></el-form-item
        ><el-form-item label="名称" required
          ><el-input
            v-model="form.record_name"
            :maxlength="128"
            :placeholder="kind === 'customers' ? '业务简称或代号' : '名称'"
        /></el-form-item>
        <el-form-item v-if="kind === 'customers'" label="对账参考"
          ><el-select v-model="form.reconciliation_mode_code"
            ><el-option value="by_item" label="按货品" /><el-option
              value="by_order"
              label="按工单" /></el-select
          ><small>当前确认数量仍以本司已出货数量为准。</small></el-form-item
        >
        <template v-if="kind === 'processes'">
          <el-form-item label="项目阶段"
            ><RemoteSelect
              v-model="form.project_stage_id"
              :context-key="form.org_id"
              :disabled="!form.org_id"
              :load-options="
                (value) => archiveOptions('project-stages', form.org_id, value)
              "
              :initial-option="initialReference('project_stage')"
              placeholder="选择阶段（可选）"
          /></el-form-item>
          <el-form-item label="默认工艺要求"
            ><RemoteSelect
              v-model="form.requirement_id"
              :context-key="form.org_id"
              :disabled="!form.org_id"
              :load-options="
                (value) => archiveOptions('requirements', form.org_id, value)
              "
              :initial-option="initialReference('requirement')"
              placeholder="选择要求（可选）"
          /></el-form-item>
          <el-form-item label="前置工艺"
            ><el-select
              v-model="form.previous_process_ids"
              multiple
              filterable
              remote
              :disabled="!form.org_id"
              :remote-method="searchPrevious"
              :loading="previousLoading"
              placeholder="可多选；禁止循环"
              @visible-change="(value) => value && searchPrevious()"
              ><el-option
                v-for="row in previousOptions"
                :key="row.value"
                :value="row.value"
                :label="row.label" /></el-select
          ></el-form-item>
          <el-form-item label="排程执行类别"
            ><el-select
              v-model="form.execution_kind_code"
              clearable
              placeholder="待工程确认"
              @change="
                (value) => {
                  form.is_equipment_required = value
                    ? ['machine', 'machine_inspection'].includes(value)
                    : null;
                  if (value === 'external')
                    form.processing_type_code = 'outsourced';
                }
              "
              ><el-option
                label="机器加工（占用本厂设备）"
                value="machine" /><el-option
                label="人工操作（不占机器）"
                value="manual" /><el-option
                label="人工检验（需检验资格）"
                value="inspection" /><el-option
                label="设备检验（如三坐标）"
                value="machine_inspection" /><el-option
                label="委外（不占本厂机器）"
                value="external" /></el-select
            ><small
              >检验须明确设为检验工艺；空白不根据名称推断。机器能力在设备档案维护。</small
            ></el-form-item
          >
          <el-form-item label="加工类型"
            ><el-select v-model="form.processing_type_code"
              ><el-option value="in_house" label="自制" /><el-option
                value="outsourced"
                label="委外（档案标记）" /><el-option
                value="purchased"
                label="采购（档案标记）" /></el-select
          ></el-form-item>
          <el-form-item label="计件工艺"
            ><el-switch v-model="form.is_piecework" /><small
              >档案标记，不自动计算工资。</small
            ></el-form-item
          ><el-form-item label="需要检验"
            ><el-switch v-model="form.is_quality_required"
          /></el-form-item>
        </template>
        <template v-if="kind === 'equipment'"
          ><el-form-item label="适用工艺"
            ><el-select
              v-model="form.process_ids"
              multiple
              filterable
              remote
              :disabled="!form.org_id"
              :remote-method="searchPrevious"
              :loading="previousLoading"
              placeholder="可选择多个工艺；留空表示通用设备"
              @visible-change="(value) => value && searchPrevious()"
              ><el-option
                v-for="item in previousOptions"
                :key="item.value"
                :value="item.value"
                :label="item.label" /></el-select></el-form-item
          ><el-form-item label="工作中心"
            ><el-input
              v-model="form.work_center_name"
              :maxlength="128"
              placeholder="如：机加车间" /></el-form-item
        ></template>
        <el-form-item v-if="kind === 'requirements'" label="定价标准说明"
          ><el-input
            v-model="form.pricing_description"
            type="textarea"
            :maxlength="1000"
            placeholder="供人工参考，不自动计价"
        /></el-form-item>
        <el-form-item label="说明"
          ><el-input
            v-model="form.description"
            type="textarea"
            :rows="3"
            :maxlength="4000" /></el-form-item
        ><el-form-item label="显示顺序"
          ><el-input-number
            v-model="form.sort_no"
            :min="0"
            :max="100000"
            :precision="0" /></el-form-item
        ><el-form-item label="启用"
          ><el-switch v-model="form.is_active"
        /></el-form-item> </el-form
      ><small>停用后不能供新记录选用，已创建工单的快照保持不变。</small>
      <template #footer
        ><el-button @click="visible = false">取消</el-button
        ><el-button type="primary" :loading="saving" @click="save"
          >保存</el-button
        ></template
      >
    </el-dialog>
  </div>
</template>
<style scoped>
.archive-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

h2 {
  margin: 0;
}

small {
  color: var(--el-text-color-secondary);
}

.el-pagination {
  margin-top: 20px;
}
</style>
