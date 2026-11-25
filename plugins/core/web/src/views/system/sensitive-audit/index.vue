<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { hasPerms } from "@/utils/auth";
import { message } from "@/utils/message";
import { getHttpErrorMessage } from "@/utils/http";
import { PureTableBar } from "@/components/RePureTableBar";
import { useRenderIcon } from "@/components/ReIcon/src/hooks";
import Refresh from "~icons/ep/refresh";
import {
  getAuditOptions,
  getSensitiveAudits,
  getAuditDetail,
  type SensitiveAuditItem
} from "@/api/sensitiveAudit";

defineOptions({ name: "SensitiveDataAudit" });
const loading = ref(false),
  detailLoading = ref(false),
  visible = ref(false);
const rows = ref<SensitiveAuditItem[]>([]),
  current = ref<SensitiveAuditItem>();
const targets = ref<{ value: string; label: string }[]>([]);
const labels = computed(() =>
  Object.fromEntries(targets.value.map(item => [item.value, item.label]))
);
const actions: Record<string, string> = {
  read: "查看",
  create: "新增",
  update: "修改",
  delete: "删除",
  export: "导出",
  import: "导入",
  approve: "审批",
  submit: "提交"
};
const query = reactive({
  target_type_code: "",
  target_id: "",
  actor_name: "",
  action_code: "",
  successful: undefined as boolean | undefined
});
const range = ref<string[]>([]);
const page = ref(1),
  pageSize = ref(20),
  total = ref(0);
const tableRef = ref();
const pagination = computed(() => ({
  currentPage: page.value,
  pageSize: pageSize.value,
  total: total.value,
  pageSizes: [20, 50, 100],
  background: true
}));
const columns: TableColumnList = [
  { label: "时间", prop: "created_at", minWidth: 175 },
  { label: "操作人", prop: "actor_name", minWidth: 120 },
  {
    label: "数据类型",
    prop: "target_type_code",
    minWidth: 135,
    slot: "targetType"
  },
  { label: "动作", prop: "action_code", width: 90, slot: "action" },
  { label: "对象 ID", prop: "target_id", minWidth: 220 },
  { label: "HTTP 状态", prop: "http_status", width: 110, slot: "httpStatus" },
  { label: "方法", prop: "request_method", width: 85 },
  { label: "接口", prop: "request_path", minWidth: 230 },
  {
    label: "操作",
    fixed: "right",
    width: 90,
    slot: "operation",
    hide: () => !hasPerms("operation_log:detail")
  }
];

function onFullscreen() {
  tableRef.value?.setAdaptive();
}
function onPageSizeChange(value: number) {
  pageSize.value = value;
  void load(true);
}
function onPageChange(value: number) {
  page.value = value;
  void load();
}

async function load(reset = false) {
  if (reset) page.value = 1;
  if (
    query.target_id &&
    !/^[\da-f]{8}(-[\da-f]{4}){3}-[\da-f]{12}$/i.test(query.target_id.trim())
  ) {
    message("对象 ID 须为有效 UUID", { type: "warning" });
    return;
  }
  loading.value = true;
  try {
    const { data } = await getSensitiveAudits({
      ...query,
      target_id: query.target_id.trim() || undefined,
      successful:
        typeof query.successful === "boolean" ? query.successful : undefined,
      page: page.value,
      page_size: pageSize.value,
      created_start: range.value?.[0],
      created_end: range.value?.[1]
    });
    rows.value = data.items;
    total.value = data.total;
  } catch (e) {
    rows.value = [];
    total.value = 0;
    message(getHttpErrorMessage(e, "敏感审计日志加载失败"), { type: "error" });
  } finally {
    loading.value = false;
  }
}
function reset() {
  Object.assign(query, {
    target_type_code: "",
    target_id: "",
    actor_name: "",
    action_code: "",
    successful: undefined
  });
  range.value = [];
  void load(true);
}
async function detail(row: SensitiveAuditItem) {
  detailLoading.value = true;
  try {
    current.value = (await getAuditDetail(row.id)).data;
    visible.value = true;
  } catch (e) {
    message(getHttpErrorMessage(e, "审计详情加载失败"), { type: "error" });
  } finally {
    detailLoading.value = false;
  }
}
onMounted(async () => {
  try {
    targets.value = (await getAuditOptions()).data.targets;
  } catch (e) {
    message(getHttpErrorMessage(e, "审计类型加载失败"), { type: "error" });
  }
  await load();
});
</script>

<template>
  <ReListPresentation>
  <div class="main list-page list-presentation-container">
    <el-alert
      title="记录已接入模块的查看、修改和导出请求。日志只读，不保存业务数据原文；HTTP 状态表示服务端请求结果，不代表用户已完成文件下载。"
      type="info"
      :closable="false"
      class="mb-4"
    />
    <ReListHeading title="敏感数据审计" />
    <section class="list-query-panel">
      <el-form
        :inline="true"
        :model="query"
        class="search-form bg-bg_color w-full pl-8 pt-3 list-filters"
        @submit.prevent="load(true)"
      >
        <el-form-item label="数据类型"
          ><el-select
            v-model="query.target_type_code"
            clearable
            filterable
            allow-create
            default-first-option
            class="filter-control"
            placeholder="请选择类型"
          >
            <el-option
              v-for="item in targets"
              :key="item.value"
              :value="item.value"
              :label="item.label"
            /> </el-select
        ></el-form-item>
        <el-form-item label="操作人"
          ><el-input
            v-model="query.actor_name"
            class="filter-control"
            clearable
            placeholder="请输入操作人名称"
        /></el-form-item>
        <el-form-item label="对象 ID"
          ><el-input
            v-model="query.target_id"
            class="filter-control object-id-control"
            clearable
            placeholder="请输入业务对象 UUID"
        /></el-form-item>
        <el-form-item label="动作"
          ><el-select
            v-model="query.action_code"
            clearable
            class="filter-control"
            placeholder="请选择动作"
            ><el-option
              v-for="(label, value) in actions"
              :key="value"
              :value="value"
              :label="label" /></el-select
        ></el-form-item>
        <el-form-item label="HTTP 结果"
          ><el-select
            v-model="query.successful"
            clearable
            class="filter-control"
            placeholder="请选择结果"
            ><el-option label="成功" :value="true" /><el-option
              label="失败"
              :value="false" /></el-select
        ></el-form-item>
        <el-form-item label="时间"
          ><el-date-picker
            v-model="range"
            class="time-range-control"
            type="datetimerange"
            value-format="YYYY-MM-DDTHH:mm:ss"
            range-separator="至"
            start-placeholder="开始时间"
            end-placeholder="结束时间"
        /></el-form-item>
        <el-form-item
          ><el-button
            data-list-query="search"
            type="primary"
            :icon="useRenderIcon('ri/search-line')"
            :loading="loading"
            @click="load(true)"
            >搜索</el-button
          ><el-button
            data-list-query="reset"
            :icon="useRenderIcon(Refresh)"
            @click="reset"
            >重置</el-button
          ></el-form-item
        >
      </el-form>
      <PureTableBar
        :list-heading="false"
        title="敏感数据审计"
        :columns="columns"
        @refresh="load()"
        @fullscreen="onFullscreen"
      >
        <template v-slot="{ size, dynamicColumns }">
          <ReListTable
            list-key="index-0"
            engine="pure"
            :list-refresh="load"
            ref="tableRef"
            row-key="id"
            align-whole="center"
            table-layout="auto"
            showOverflowTooltip
            adaptive
            :adaptiveConfig="{ offsetBottom: 108 }"
            :loading="loading"
            :size="size"
            :data="rows"
            :columns="dynamicColumns"
            :pagination="{ ...pagination, size }"
            :header-cell-style="{
              background: 'var(--el-fill-color-light)',
              color: 'var(--el-text-color-primary)'
            }"
            @page-size-change="onPageSizeChange"
            @page-current-change="onPageChange"
          >
            <template #targetType="{ row }">{{
              labels[row.target_type_code] || row.target_type_code
            }}</template>
            <template #action="{ row }">{{
              actions[row.action_code] || row.action_code
            }}</template>
            <template #httpStatus="{ row }"
              ><el-tag :type="row.http_status >= 400 ? 'danger' : 'success'">{{
                row.http_status
              }}</el-tag></template
            >
            <template #operation="{ row }"
              ><el-button
                data-action="view"
                link
                type="primary"
                :size="size"
                :loading="detailLoading"
                @click="detail(row)"
                >查看</el-button
              ></template
            >
          </ReListTable>
        </template>
      </PureTableBar>
    </section>
    <el-dialog v-model="visible" title="审计详情" width="min(700px, 92vw)">
      <el-descriptions v-if="current" :column="1" border>
        <el-descriptions-item label="请求关联 ID">{{
          current.request_id
        }}</el-descriptions-item>
        <el-descriptions-item label="操作人"
          >{{ current.actor_name }}（{{
            current.actor_user_id
          }}）</el-descriptions-item
        >
        <el-descriptions-item label="数据类型">{{
          labels[current.target_type_code] || current.target_type_code
        }}</el-descriptions-item>
        <el-descriptions-item label="动作">{{
          actions[current.action_code] || current.action_code
        }}</el-descriptions-item>
        <el-descriptions-item label="业务对象">{{
          current.target_id || "列表或汇总请求"
        }}</el-descriptions-item>
        <el-descriptions-item label="接口"
          >{{ current.request_method }}
          {{ current.request_path }}</el-descriptions-item
        >
        <el-descriptions-item label="HTTP 状态">{{
          current.http_status
        }}</el-descriptions-item>
        <el-descriptions-item label="来源 IP">{{
          current.ip_address
        }}</el-descriptions-item>
        <el-descriptions-item label="时间">{{
          current.created_at
        }}</el-descriptions-item>
      </el-descriptions>
    </el-dialog>
  </div>

  </ReListPresentation>
</template>

<style lang="scss" scoped>
.search-form {
  padding-right: 20px;

  :deep(.el-form-item) {
    margin-bottom: 12px;
  }

  :deep(.filter-control) {
    flex-shrink: 0;
    width: 180px;
  }

  :deep(.object-id-control) {
    width: 260px;
  }

  :deep(.time-range-control) {
    flex-grow: 0;
    width: 380px;
  }
}
</style>
