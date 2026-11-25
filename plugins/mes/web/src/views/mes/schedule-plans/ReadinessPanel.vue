<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { getHttpErrorMessage } from "@/utils/http";
import { message, actionMessage } from "@/utils/message";
import {
  savePlanReadiness,
  type PlanDetail,
} from "@plugins/mes/web/src/api/mesSchedulePlans";
const props = defineProps<{ plan: PlanDetail; editable: boolean }>();
const emit = defineEmits<{ saved: [] }>();
const rows = ref<
  Array<{
    work_order_id: string;
    work_order_no: string;
    readiness_kind_code: "material" | "drawing" | "program" | "tool";
    expected_at: Date;
    is_confirmed: boolean;
    version_no: number;
  }>
>([]);
const error = ref(""),
  busy = ref(false);
const labels = {
  material: "材料",
  drawing: "图纸",
  program: "程序",
  tool: "刀具",
};
watch(
  () => props.plan,
  (plan) => {
    rows.value = (plan.readiness || []).map((row) => ({
      ...row,
      expected_at: new Date(row.expected_at),
      is_confirmed: !!row.confirmed_at,
      work_order_no:
        plan.operations.find((op) => op.work_order_id === row.work_order_id)
          ?.work_order_no || row.work_order_id,
    }));
  },
  { immediate: true },
);
async function save() {
  if (rows.value.some((r) => !r.expected_at)) {
    actionMessage("请填写全部预计就绪时间", "warning");
    return;
  }
  busy.value = true;
  try {
    await savePlanReadiness(
      props.plan.id,
      rows.value.map((row) => ({
        work_order_id: row.work_order_id,
        readiness_kind_code: row.readiness_kind_code,
        expected_at: row.expected_at.toISOString(),
        is_confirmed: row.is_confirmed,
        version_no: row.version_no,
      })),
    );
    message("就绪条件已保存", { type: "success" });
    emit("saved");
  } catch (e) {
    actionMessage(getHttpErrorMessage(e, "保存实际就绪失败"));
  } finally {
    busy.value = false;
  }
}
</script>
<template>
  <el-card v-if="rows.length" shadow="never"
    ><h3>实际开工就绪</h3>
    <p class="muted">
      预计到时不会自动放行。正式方案应用后，可由排产员逐项确认实际就绪；生产开工仍会检查。
    </p>
    <el-form :disabled="!editable || busy" @submit.prevent="save"
      ><el-table :data="rows" border
        ><el-table-column
          prop="work_order_no"
          label="货品工单"
          min-width="190"
        /><el-table-column label="条件" width="120"
          ><template #default="{ row }">{{
            labels[row.readiness_kind_code as keyof typeof labels]
          }}</template></el-table-column
        ><el-table-column label="预计就绪时间" min-width="230"
          ><template #default="{ row }"
            ><el-date-picker
              v-model="row.expected_at"
              type="datetime" /></template></el-table-column
        ><el-table-column label="实际确认" min-width="170"
          ><template #default="{ row }"
            ><el-checkbox v-model="row.is_confirmed"
              >实际已就绪</el-checkbox
            ></template
          ></el-table-column
        ></el-table
      >
      <div v-if="editable" class="erp-form-actions">
        <el-button type="primary" native-type="submit" :loading="busy"
          >保存就绪确认</el-button
        >
      </div></el-form
    >
  </el-card>
</template>
<style scoped>
h3 {
  margin-bottom: 16px;
}
</style>
