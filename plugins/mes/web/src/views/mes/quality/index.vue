<script setup lang="ts">
import ListPagination from "@/components/ListPagination/index.vue";
import { computed, onBeforeUnmount, onMounted, reactive, ref } from "vue";
import { ElMessageBox } from "element-plus";
import { hasPerms } from "@/utils/auth";
import { getHttpErrorMessage } from "@/utils/http";
import { message, actionMessage } from "@/utils/message";
import {
  getQualityTasks,
  getQualityTask,
  submitQualityInspection,
  type QualityDetail,
  type QualityTask,
} from "@plugins/mes/web/src/api/mesQuality";
import { formatMesDate, mesStatusType } from "../shared";
defineOptions({ name: "MesQuality" });
const filters = reactive({ keyword: "", status_code: "waiting_quality" });
const rows = ref<QualityTask[]>([]),
  page = ref(1),
  size = ref(10),
  total = ref(0);
const loading = ref(false),
  error = ref(""),
  visible = ref(false),
  detailLoading = ref(false),
  saving = ref(false);
const detail = ref<QualityDetail>(),
  detailError = ref("");
const form = reactive({
  result_code: "pass" as "pass" | "fail",
  note: "",
  rework_operation_id: "",
});
let listRequest = 0,
  detailRequest = 0,
  lastPayload = "",
  idempotencyKey = "";
const canInspect = computed(() =>
  Boolean(
    hasPerms("mes:quality:inspect") &&
    detail.value?.status_code === "waiting_quality" &&
    ["released", "in_progress"].includes(
      detail.value.work_order_status_code || "",
    ) &&
    !detailLoading.value,
  ),
);
async function load() {
  const current = ++listRequest;
  loading.value = true;
  error.value = "";
  try {
    const result = await getQualityTasks({
      ...filters,
      page: page.value,
      page_size: size.value,
    });
    if (current === listRequest) {
      rows.value = result.data.items;
      total.value = result.data.total;
    }
  } catch (cause) {
    if (current === listRequest) {
      rows.value = [];
      total.value = 0;
      error.value = getHttpErrorMessage(cause, "检验任务读取失败");
    }
  } finally {
    if (current === listRequest) loading.value = false;
  }
}
function search() {
  page.value = 1;
  return load();
}
async function open(id: string) {
  if (saving.value) return;
  const current = ++detailRequest;
  visible.value = true;
  detail.value = undefined;
  detailError.value = "";
  detailLoading.value = true;
  form.result_code = "pass";
  form.note = "";
  form.rework_operation_id = "";
  lastPayload = idempotencyKey = "";
  try {
    const result = await getQualityTask(id);
    if (current === detailRequest) detail.value = result.data;
  } catch (cause) {
    if (current === detailRequest)
      detailError.value = getHttpErrorMessage(cause, "检验详情读取失败");
  } finally {
    if (current === detailRequest) detailLoading.value = false;
  }
}
function close() {
  ++detailRequest;
  detail.value = undefined;
  detailLoading.value = false;
}
async function submit() {
  if (saving.value || !canInspect.value || !detail.value) return;
  const selected = detail.value;
  const note = form.note.trim() || null;
  if (form.result_code === "fail" && !note) {
    actionMessage("请填写不合格原因及返工要求", "warning");
    return;
  }
  const result_code = form.result_code;
  const payload = JSON.stringify({
    id: selected.id,
    version_no: selected.version_no,
    result_code,
    note,
    rework_operation_id: form.rework_operation_id,
  });
  if (payload !== lastPayload) {
    lastPayload = payload;
    idempotencyKey = crypto.randomUUID();
  }
  saving.value = true;
  try {
    await ElMessageBox.confirm(
      result_code === "pass"
        ? "确认检验合格？报足计划后将放行该工序。"
        : "确认退回原工序返工？复检通过前不能继续后序或入库，返工不重复计产。",
      "提交工序检验",
      {
        type: "warning",
        confirmButtonText: "确认提交",
        cancelButtonText: "取消",
      },
    );
    await submitQualityInspection(selected.id, {
      version_no: selected.version_no,
      result_code,
      note,
      idempotency_key: idempotencyKey,
      production_phase_code: selected.schedule_context?.production_phase_code,
      rework_operation_id:
        result_code === "fail"
          ? form.rework_operation_id || undefined
          : undefined,
    });
    message(
      result_code === "pass"
        ? "检验结果已保存"
        : "已退回原工序，请重新开始生产并在结束后复检",
      { type: "success" },
    );
    // 成功后清空旧修订；详情刷新失败时也不允许用旧数据再次提交。
    detail.value = undefined;
    saving.value = false;
    await Promise.all([open(selected.id), load()]);
  } catch (cause) {
    if (!["cancel", "close"].includes(cause as string))
      actionMessage(getHttpErrorMessage(cause, "检验提交失败，请刷新详情后重试"));
  } finally {
    saving.value = false;
  }
}
onMounted(load);
onBeforeUnmount(() => {
  ++listRequest;
  ++detailRequest;
});
</script>

<template>
  <div class="mes-page">
    <h2>工序检验</h2>
    <p>
      检验当前整道工序的报工结果；不合格退回原工序返工，重新结束执行后复检。
    </p>
    <el-card shadow="never">
      <el-form inline @submit.prevent="search">
        <el-form-item label="搜索"
          ><el-input
            v-model="filters.keyword"
            placeholder="工单 / 产品 / 工序"
            maxlength="128"
            clearable
            @keyup.enter="search"
        /></el-form-item>
        <el-form-item label="状态"
          ><el-select v-model="filters.status_code" style="width: 145px">
            <el-option label="待检验" value="waiting_quality" /><el-option
              label="待执行 / 返工"
              value="pending"
            />
            <el-option label="已完成" value="completed" /><el-option
              label="全部"
              value=""
            /> </el-select
        ></el-form-item>
        <el-form-item
          ><el-button type="primary" @click="search">查询</el-button
          ><el-button
            @click="
              Object.assign(filters, {
                keyword: '',
                status_code: 'waiting_quality',
              });
              search();
            "
            >重置</el-button
          ></el-form-item
        >
      </el-form>
      <el-alert v-if="error" :title="error" type="error" :closable="false" />
      <el-table v-loading="loading" :data="rows" row-key="id">
        <el-table-column prop="work_order_no" label="工单号" min-width="180" />
        <el-table-column
          prop="product_item_name"
          label="产品"
          min-width="180"
        />
        <el-table-column label="工序" min-width="170"
          ><template #default="{ row }"
            >{{ row.operation_no }} · {{ row.operation_name }}</template
          ></el-table-column
        >
        <el-table-column label="计划 / 申报合格 / 报废 / 返工" min-width="250"
          ><template #default="{ row }"
            >{{ row.planned_quantity }} / {{ row.good_quantity }} /
            {{ row.scrap_quantity }} / {{ row.rework_quantity }}
            {{ row.unit_name }}</template
          ></el-table-column
        >
        <el-table-column label="状态" width="110"
          ><template #default="{ row }"
            ><el-tag :type="mesStatusType(row.status_code)">{{
              row.status_label
            }}</el-tag></template
          ></el-table-column
        >
        <el-table-column label="操作" width="140" fixed="right"
          ><template #default="{ row }"
            ><el-button
              link
              type="primary"
              :disabled="saving"
              @click="open(row.id)"
              >检验 / 查看记录</el-button
            ></template
          ></el-table-column
        >
      </el-table>
      <ListPagination
        v-model:current-page="page"
        v-model:page-size="size"
        :total="total"
        layout="total, sizes, prev, pager, next"
        @current-change="load"
        @size-change="search"
      />
    </el-card>
    <el-drawer
      v-model="visible"
      title="工序检验及记录"
      size="min(800px, 96vw)"
      :show-close="!saving"
      :close-on-click-modal="!saving"
      :close-on-press-escape="!saving"
      @closed="close"
    >
      <section v-loading="detailLoading">
        <el-alert
          v-if="detailError"
          :title="detailError"
          type="error"
          :closable="false"
        />
        <template v-if="detail">
          <h3>{{ detail.work_order_no }} · {{ detail.operation_name }}</h3>
          <p>{{ detail.product_item_name }} · {{ detail.status_label }}</p>
          <el-alert
            v-if="detail.schedule_context"
            :closable="false"
            type="info"
            :title="`${detail.schedule_context.phase_label}检验 · 本批次数量 ${detail.schedule_context.planned_quantity}${detail.unit_name}`"
          >
            {{
              detail.schedule_context.production_phase_code === "first"
                ? "这是完整路线首件检验。合格放行后才能开始剩余批量，首件计入交付数量。"
                : "这是剩余批量检验。全部实际生产及检验完成后才完结工单。"
            }}
          </el-alert>
          <el-descriptions :column="2" border>
            <el-descriptions-item label="计划数量"
              >{{ detail.planned_quantity }}
              {{ detail.unit_name }}</el-descriptions-item
            >
            <el-descriptions-item label="申报合格"
              >{{ detail.good_quantity }}
              {{ detail.unit_name }}</el-descriptions-item
            >
            <el-descriptions-item label="申报报废">{{
              detail.scrap_quantity
            }}</el-descriptions-item>
            <el-descriptions-item label="申报返工">{{
              detail.rework_quantity
            }}</el-descriptions-item>
          </el-descriptions>
          <el-form
            v-if="canInspect"
            :disabled="saving"
            label-position="top"
            class="inspection-form"
            @submit.prevent="submit"
          >
            <el-form-item label="检验结论"
              ><el-radio-group v-model="form.result_code"
                ><el-radio value="pass">合格放行</el-radio
                ><el-radio value="fail"
                  >不合格退回返工</el-radio
                ></el-radio-group
              ></el-form-item
            >
            <el-form-item
              :label="
                form.result_code === 'fail'
                  ? '不合格原因及返工要求（必填）'
                  : '检验说明'
              "
              :required="form.result_code === 'fail'"
              ><el-input
                v-model="form.note"
                type="textarea"
                :rows="3"
                maxlength="1000"
                show-word-limit
            /></el-form-item>
            <el-form-item
              v-if="form.result_code === 'fail' && detail.schedule_context"
              label="返工起始工序（默认当前工序）"
              ><el-select v-model="form.rework_operation_id" clearable
                ><el-option
                  v-for="option in detail.rework_options || []"
                  :key="option.value"
                  v-bind="option" /></el-select
            ></el-form-item>
            <div class="erp-form-actions">
              <el-button type="primary" :loading="saving" @click="submit"
                >提交检验</el-button
              >
            </div>
          </el-form>
          <el-alert
            v-else
            title="当前仅可查看记录。工序须待检验、工单可执行且账号拥有检验权限才能提交。"
            type="info"
            :closable="false"
            class="inspection-form"
          />
          <h3>检验记录（最近 100 次）</h3>
          <el-table :data="detail.inspections" row-key="id">
            <el-table-column label="检验时间" min-width="175"
              ><template #default="{ row }">{{
                formatMesDate(row.created_at)
              }}</template></el-table-column
            >
            <el-table-column label="结果" width="135"
              ><template #default="{ row }"
                ><el-tag
                  :type="row.result_code === 'pass' ? 'success' : 'danger'"
                  >{{
                    row.result_code === "pass" ? "合格放行" : "退回返工"
                  }}</el-tag
                ></template
              ></el-table-column
            >
            <el-table-column label="当时合格 / 报废 / 返工" min-width="180"
              ><template #default="{ row }"
                >{{ row.good_quantity }} / {{ row.scrap_quantity }} /
                {{ row.rework_quantity }}</template
              ></el-table-column
            >
            <el-table-column
              prop="note"
              label="检验说明"
              min-width="200"
              show-overflow-tooltip
            />
          </el-table>
        </template>
      </section>
    </el-drawer>
  </div>
</template>
<style scoped>
.inspection-form {
  margin: 20px 0;
}

.el-pagination {
  margin-top: 16px;
}
</style>
