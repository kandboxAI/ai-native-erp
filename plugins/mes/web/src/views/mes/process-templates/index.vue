<script setup lang="ts">
import ListPagination from "@/components/ListPagination/index.vue";
import { onMounted, ref } from "vue";
import draggable from "vuedraggable/src/vuedraggable";
import {
  getMesProcessTemplates,
  saveMesProcessTemplate,
  getMesOrgOptions,
  getMesProductOptions,
  type MesProcessTemplate,
} from "@plugins/mes/web/src/api/mes";
import { hasPerms } from "@/utils/auth";
import { message } from "@/utils/message";
import RemoteSelect from "../components/RemoteSelect.vue";
import ArchiveOperationPicker from "../components/ArchiveOperationPicker.vue";
defineOptions({ name: "MesProcessTemplates" });
type Operation = MesProcessTemplate["operations"][number] & { key: number };
let nextKey = 0;
const keyword = ref(""),
  page = ref(1),
  size = ref(10),
  total = ref(0),
  rows = ref<MesProcessTemplate[]>([]);
const loading = ref(false),
  error = ref(""),
  saving = ref(false),
  visible = ref(false);
const form = ref<
  Omit<MesProcessTemplate, "operations"> & { operations: Operation[] }
>();
let request = 0;
async function load() {
  const current = ++request;
  loading.value = true;
  error.value = "";
  try {
    const result = await getMesProcessTemplates({
      keyword: keyword.value,
      page: page.value,
      page_size: size.value,
    });
    if (current === request) {
      rows.value = result.data.items;
      total.value = result.data.total;
    }
  } catch (cause: any) {
    if (current === request) {
      rows.value = [];
      total.value = 0;
      error.value = cause?.message || "模板加载失败";
    }
  } finally {
    if (current === request) loading.value = false;
  }
}
function search() {
  page.value = 1;
  load();
}
function edit(value?: Record<string, any>) {
  const row = value as MesProcessTemplate | undefined;
  form.value = row
    ? {
        ...row,
        operations: row.operations.map((op) => ({ ...op, key: ++nextKey })),
      }
    : {
        org_id: "",
        template_no: "",
        template_name: "",
        product_item_id: null,
        is_active: true,
        operations: [
          { key: ++nextKey, operation_no: "10", operation_name: "" },
        ],
      };
  visible.value = true;
}
function addOperation() {
  if (saving.value || !form.value || form.value.operations.length >= 100)
    return;
  const numbers = new Set(form.value.operations.map((op) => op.operation_no));
  let next = 10;
  while (numbers.has(String(next))) next += 10;
  form.value.operations.push({
    key: ++nextKey,
    operation_no: String(next),
    operation_name: "",
  });
}
async function save() {
  if (saving.value || !form.value) return;
  const current = form.value;
  if (
    !current.org_id ||
    !current.template_no.trim() ||
    !current.template_name.trim() ||
    !current.operations.length ||
    current.operations.some(
      (op) => !op.operation_no.trim() || !op.operation_name.trim(),
    )
  ) {
    message("请填写组织、模板编号和名称，并至少填写一道工序的编号及名称", {
      type: "warning",
    });
    return;
  }
  if (
    new Set(current.operations.map((op) => op.operation_no.trim())).size !==
    current.operations.length
  ) {
    message("工序编号不能重复", { type: "warning" });
    return;
  }
  saving.value = true;
  try {
    const { operations, ...head } = current;
    await saveMesProcessTemplate({
      ...head,
      product_item_id: head.product_item_id || null,
      operations: operations.map(({ key, ...op }) => ({
        ...op,
        operation_no: op.operation_no.trim(),
        operation_name: op.operation_name.trim(),
      })),
    });
    message("模板已保存；已有工单保持原工序配置", { type: "success" });
    visible.value = false;
    await load();
  } catch (cause: any) {
    message(cause?.message || "模板保存失败，请刷新版本后重试", {
      type: "warning",
    });
  } finally {
    saving.value = false;
  }
}
onMounted(load);
</script>
<template>
  <div class="mes-page">
    <div class="heading">
      <div>
        <h2>工艺路线</h2>
        <p class="muted">
          定义可复用的工序顺序和说明。选用时复制到工单，后续修订不修改已有工单。
        </p>
      </div>
      <el-button
        v-if="hasPerms('mes:process_template:manage')"
        type="primary"
        @click="edit()"
        >新增模板</el-button
      >
    </div>
    <el-card shadow="never"
      ><el-form inline @submit.prevent="search"
        ><el-form-item label="搜索"
          ><el-input
            v-model="keyword"
            clearable
            maxlength="128"
            placeholder="模板编号 / 名称"
            @keyup.enter="search" /></el-form-item
        ><el-form-item
          ><el-button type="primary" @click="search">查询</el-button
          ><el-button
            @click="
              keyword = '';
              search();
            "
            >重置</el-button
          ></el-form-item
        ></el-form
      >
      <el-alert v-if="error" :title="error" type="error" :closable="false" />
      <el-table v-loading="loading" :data="rows"
        ><el-table-column
          prop="template_no"
          label="模板编号"
          min-width="150"
        /><el-table-column
          prop="template_name"
          label="模板名称"
          min-width="190"
        /><el-table-column
          prop="version_no"
          label="修订"
          width="90"
        /><el-table-column label="工序" min-width="300"
          ><template #default="{ row }">{{
            row.operations.map((op) => op.operation_name).join(" → ")
          }}</template></el-table-column
        ><el-table-column label="状态" width="100"
          ><template #default="{ row }"
            ><el-tag :type="row.is_active ? 'success' : 'info'">{{
              row.is_active ? "可选用" : "已停用"
            }}</el-tag></template
          ></el-table-column
        ><el-table-column label="操作" width="110"
          ><template #default="{ row }"
            ><el-button link type="primary" @click="edit(row)">{{
              hasPerms("mes:process_template:manage") ? "查看 / 修订" : "查看"
            }}</el-button></template
          ></el-table-column
        ></el-table
      >
      <ListPagination
        v-model:current-page="page"
        v-model:page-size="size"
        :total="total"
        layout="total, sizes, prev, pager, next"
        @current-change="load"
        @size-change="search"
      />
    </el-card>
    <el-dialog
      v-model="visible"
      :title="form?.id ? '工艺路线详情 / 修订' : '新增工艺路线'"
      width="min(1050px, 96vw)"
      top="5vh"
      :close-on-click-modal="false"
      :close-on-press-escape="!saving"
      :show-close="!saving"
      destroy-on-close
      append-to-body
    >
      <el-form
        v-if="form"
        :disabled="saving || !hasPerms('mes:process_template:manage')"
        label-position="top"
      >
        <div class="basic">
          <el-form-item label="组织（必填）"
            ><RemoteSelect
              v-model="form.org_id"
              :disabled="!!form.id || !hasPerms('mes:process_template:manage')"
              :initial-option="
                form.id
                  ? { value: form.org_id, label: '模板所属组织' }
                  : undefined
              "
              :load-options="(keyword) => getMesOrgOptions(keyword, true)"
              placeholder="选择组织"
              auto-select-single /></el-form-item
          ><el-form-item label="模板编号（必填）"
            ><el-input
              v-model="form.template_no"
              maxlength="64" /></el-form-item
          ><el-form-item label="模板名称（必填）"
            ><el-input v-model="form.template_name" maxlength="128"
          /></el-form-item>
          <el-form-item label="适用产品（留空表示本组织通用）"
            ><RemoteSelect
              v-model="form.product_item_id"
              :initial-option="
                form.product_item_id
                  ? {
                      value: form.product_item_id,
                      label: '已选产品（可按编号重选）',
                    }
                  : undefined
              "
              :disabled="!hasPerms('mes:process_template:manage')"
              :load-options="(keyword) => getMesProductOptions(keyword, true)"
              placeholder="选择产品或留空" /></el-form-item
          ><el-form-item label="可供新工单选用"
            ><el-switch v-model="form.is_active"
          /></el-form-item>
        </div>
        <div class="heading">
          <h3>工序（拖动手柄排序）</h3>
          <el-button
            :disabled="form.operations.length >= 100"
            @click="addOperation"
            >添加工序</el-button
          >
        </div>
        <div class="operation-list">
          <draggable
            v-model="form.operations"
            item-key="key"
            handle=".drag"
            :animation="150"
            :disabled="saving || !hasPerms('mes:process_template:manage')"
            ><template #item="{ element: op, index }"
              ><div class="operation">
                <ArchiveOperationPicker
                  :org-id="form.org_id"
                  :model-value="op"
                  :disabled="!hasPerms('mes:process_template:manage')"
                  @update:model-value="(value) => Object.assign(op, value)"
                />
                <div class="row">
                  <button
                    class="drag"
                    type="button"
                    :aria-label="`拖动第${index + 1}道工序`"
                  >
                    ⠿</button
                  ><strong>{{ index + 1 }}</strong
                  ><el-input
                    v-model="op.operation_no"
                    placeholder="工序号（必填）"
                    maxlength="64"
                  /><el-input
                    v-model="op.operation_name"
                    :disabled="!!op.process_id"
                    placeholder="工序名称（必填）"
                    maxlength="128"
                  /><el-button
                    type="danger"
                    link
                    @click="form.operations.splice(index, 1)"
                    >删除</el-button
                  >
                </div>
                <div class="row">
                  <el-input
                    v-model="op.work_center_name"
                    placeholder="工作中心"
                    maxlength="128"
                  /><el-input
                    v-model="op.workstation_name"
                    placeholder="工作站"
                    maxlength="128"
                  />
                </div>
                <el-input
                  v-model="op.operation_description"
                  type="textarea"
                  :rows="2"
                  maxlength="4000"
                  placeholder="工艺说明"
                />
                <el-form-item label="单件预计工时（小时）">
                  <el-input-number
                    :model-value="
                      op.standard_minutes_per_unit == null
                        ? undefined
                        : op.standard_minutes_per_unit / 60
                    "
                    :min="0.001"
                    :max="87600"
                    :precision="3"
                    :controls="false"
                    placeholder="选用后乘工序计划数量"
                    @update:model-value="
                      (value) =>
                        (op.standard_minutes_per_unit =
                          value == null
                            ? undefined
                            : Number((value * 60).toFixed(3)))
                    "
                  />
                </el-form-item>
                <p v-if="op.is_quality_required" class="muted">
                  此工序沿用检验要求；质量放行流程尚未完成。
                </p>
              </div></template
            ></draggable
          >
        </div>
      </el-form>
      <template #footer
        ><el-button :disabled="saving" @click="visible = false">关闭</el-button
        ><el-button
          v-if="hasPerms('mes:process_template:manage')"
          type="primary"
          :loading="saving"
          @click="save"
          >保存修订</el-button
        ></template
      >
    </el-dialog>
  </div>
</template>
<style scoped>
.mes-page {
  padding: 20px;
}

.heading {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
}

h2 {
  margin: 0;
}

.muted {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.basic {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 0 16px;
}

.operation-list {
  max-height: 48vh;
  overflow: auto;
}

.operation {
  padding: 14px;
  margin-bottom: 12px;
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
}

.row {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-bottom: 10px;
}

.drag {
  font-size: 24px;
  color: var(--el-text-color-secondary);
  cursor: grab;
  background: none;
  border: 0;
}

.el-pagination {
  justify-content: flex-end;
  margin-top: 20px;
}
</style>
