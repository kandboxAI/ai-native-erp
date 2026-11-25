<script setup lang="ts">
import { ref, watch } from "vue";
import {
  getMesReportDetail,
  type MesReportDetail,
} from "@plugins/mes/web/src/api/mes";
const props = defineProps<{ reportId?: string }>();
const visible = defineModel<boolean>({ default: false });
const detail = ref<MesReportDetail>(),
  loading = ref(false),
  error = ref("");
let request = 0;
async function load() {
  const current = ++request;
  loading.value = true;
  error.value = "";
  detail.value = undefined;
  try {
    const result = await getMesReportDetail(props.reportId);
    if (current === request) detail.value = result.data;
  } catch (cause: any) {
    if (current === request) error.value = cause?.message || "报工详情读取失败";
  } finally {
    if (current === request) loading.value = false;
  }
}
watch(
  () => [visible.value, props.reportId],
  () => {
    if (visible.value && props.reportId) load();
    else ++request;
  },
);
</script>
<template>
  <el-dialog
    v-model="visible"
    title="报工详情"
    width="min(700px, 96vw)"
    append-to-body
    destroy-on-close
    ><div v-loading="loading">
      <el-alert
        v-if="error"
        :title="error"
        type="error"
        :closable="false"
      /><template v-if="detail"
        ><h3>{{ detail.report_no }}</h3>
        <p>{{ detail.work_order_no }} / {{ detail.operation_name }}</p>
        <p v-if="detail.status_code === 'reversed'">
          此记录已冲销，原数值仅用于历史追溯，不再计入累计。
        </p>
        <el-descriptions :column="2" border
          ><el-descriptions-item label="合格 / 报废 / 返工"
            >{{ detail.good_quantity }} / {{ detail.scrap_quantity }} /
            {{ detail.rework_quantity }}
            {{ detail.unit_name }}</el-descriptions-item
          ><el-descriptions-item label="人工 / 机器工时"
            >{{ detail.labor_minutes ?? "—" }} /
            {{ detail.machine_minutes ?? "—" }} 分钟</el-descriptions-item
          ></el-descriptions
        >
        <p class="note">{{ detail.note || "无现场说明" }}</p>
        <p v-for="file in detail.attachments" :key="file.id">
          <a :href="file.url" target="_blank" rel="noopener noreferrer">{{
            file.file_name
          }}</a>
        </p></template
      >
    </div></el-dialog
  >
</template>
<style scoped>
.note {
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}

a {
  color: var(--el-color-primary);
}
</style>
