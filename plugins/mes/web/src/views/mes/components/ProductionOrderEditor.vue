<script setup lang="ts">
import { onBeforeUnmount, reactive, ref, watch } from "vue";
import {
  createMesProductionOrder,
  getMesOrgOptions,
  type MesOrderDefinition,
  type MesProductionOrder,
  updateMesProductionOrder,
} from "@plugins/mes/web/src/api/mes";
import { message, actionMessage } from "@/utils/message";
import { getHttpErrorMessage } from "@/utils/http";
import RemoteSelect from "./RemoteSelect.vue";
import {
  archiveOptions,
  type ArchiveOption,
} from "@plugins/mes/web/src/api/mesArchives";
import WorkOrderCreate from "./WorkOrderCreate.vue";
import { mesProcessingTypeLabel } from "../shared";
import {
  uploadProductDrawings,
  releaseProductDrawings,
  markProductDrawingsBound,
} from "../work-orders/productDrawings";

const props = defineProps<{
  purpose?: "edit" | "copy";
  initialProject?: MesProductionOrder;
  copyProducts?: MesOrderDefinition[];
}>();

const visible = defineModel<boolean>({ default: false });
const emit = defineEmits<{ created: [] }>();
const saving = ref(false);
const form = reactive({
  org_id: "",
  production_order_no: "",
  project_name: "",
  customer_id: "" as string | null,
  customer_no: "",
  customer_name: "",
  note: "",
});
const products = ref<MesOrderDefinition[]>([]);
const productVisible = ref(false);
const product = ref<MesOrderDefinition>();
const editingIndex = ref(-1);
function releaseProducts() {
  products.value.forEach((row) => releaseProductDrawings(row.drawing_files));
}
onBeforeUnmount(releaseProducts);
function removeProduct(index: number) {
  releaseProductDrawings(products.value[index].drawing_files);
  products.value.splice(index, 1);
}
watch(visible, (value) => {
  releaseProducts();
  if (value) {
    Object.assign(form, {
      org_id: "",
      production_order_no: "",
      project_name: "",
      customer_id: "" as string | null,
      customer_no: "",
      customer_name: "",
      note: "",
    });
    products.value = [];
    if (props.initialProject) {
      const data = props.initialProject;
      Object.assign(form, {
        org_id: data.org_id,
        production_order_no:
          props.purpose === "copy" ? "" : data.production_order_no,
        project_name: data.project_name,
        customer_id: data.customer_id || null,
        customer_no: data.customer_no || "",
        customer_name: data.customer_name || "",
        note: data.note || "",
      });
      products.value =
        props.purpose === "copy"
          ? (props.copyProducts || []).map((row) => ({
              ...row,
              work_order_no: "",
              drawing_files: undefined,
              drawing_attachment_ids: undefined,
              drawing_revision_label: undefined,
            }))
          : [];
    }
  }
});
watch(
  () => form.org_id,
  (value, previous) => {
    if (
      previous &&
      value !== previous &&
      props.initialProject?.org_id !== value
    ) {
      releaseProducts();
      products.value = [];
      form.customer_id = null;
      form.customer_no = "";
      form.customer_name = "";
    }
  },
);
function selectCustomer(option?: ArchiveOption) {
  form.customer_id = option?.value || null;
  form.customer_no = option?.record_no || "";
  form.customer_name = option?.record_name || "";
}
function configure(index = -1) {
  if (!form.org_id || !form.production_order_no.trim()) {
    message("请先选择组织并填写项目编号", { type: "warning" });
    return;
  }
  editingIndex.value = index;
  const used = new Set(
    [
      ...(props.purpose === "edit" ? props.initialProject?.orders || [] : []),
      ...products.value,
    ].map((row) => row.work_order_no),
  );
  let next = 1;
  while (
    used.has(
      `${form.production_order_no.trim()}-${String(next).padStart(3, "0")}`,
    )
  )
    next++;
  product.value =
    index >= 0
      ? {
          ...products.value[index],
          work_order_no:
            products.value[index].work_order_no ||
            `${form.production_order_no.trim()}-${String(index + 1).padStart(3, "0")}`,
        }
      : {
          org_id: form.org_id,
          work_order_no: `${form.production_order_no.trim()}-${String(next).padStart(3, "0")}`,
          product_item_id: "",
          planned_quantity: 1,
          priority_code: "normal",
          operations: [],
        };
  productVisible.value = true;
}
function configured(value: MesOrderDefinition) {
  if (editingIndex.value >= 0)
    releaseProductDrawings(
      products.value[editingIndex.value].drawing_files,
      value.drawing_files,
    );
  if (editingIndex.value >= 0)
    products.value.splice(editingIndex.value, 1, value);
  else products.value.push(value);
}
async function submit() {
  if (saving.value) return;
  if (
    !form.org_id ||
    !form.production_order_no.trim() ||
    !form.project_name.trim() ||
    (!products.value.length && props.purpose !== "edit")
  ) {
    message("请填写项目编号、名称并添加至少一个产品", { type: "warning" });
    return;
  }
  const numbers = products.value.map(
    (row, index) =>
      row.work_order_no.trim() ||
      `${form.production_order_no.trim()}-${String(index + 1).padStart(3, "0")}`,
  );
  if (new Set(numbers).size !== numbers.length) {
    message("产品工单号不能重复", { type: "warning" });
    return;
  }
  saving.value = true;
  try {
    const prepared: MesOrderDefinition[] = [];
    for (const row of products.value) {
      const { drawing_files, ...body } = row;
      prepared.push({
        ...body,
        drawing_attachment_ids: await uploadProductDrawings(drawing_files),
      });
    }
    const payload = {
      ...form,
      customer_id: form.customer_id || null,
      production_order_no: form.production_order_no.trim(),
      project_name: form.project_name.trim(),
      products: prepared.map((row, index) => ({
        ...row,
        work_order_no: numbers[index],
        org_id: form.org_id,
        publish: false,
      })),
    };
    if (props.purpose === "edit")
      await updateMesProductionOrder(props.initialProject.id, {
        ...payload,
        version_no: props.initialProject.version_no,
      });
    else await createMesProductionOrder(payload);
    products.value.forEach((row) =>
      markProductDrawingsBound(row.drawing_files),
    );
    message("工单与货品已保存，请配置工序后下单", {
      type: "success",
    });
    visible.value = false;
    emit("created");
  } catch (error: any) {
    actionMessage(getHttpErrorMessage(error, "创建失败，未完成的修改仍保留"));
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <el-dialog
    v-model="visible"
    :title="
      purpose === 'edit'
        ? '变更项目资料 / 追加产品'
        : purpose === 'copy'
          ? '复制项目及产品配置'
          : '新增生产项目 / 多产品工单'
    "
    width="min(1060px, 96vw)"
    top="4vh"
    :close-on-click-modal="false"
    :show-close="!saving"
    :close-on-press-escape="!saving"
    destroy-on-close
  >
    <el-form :model="form" label-position="top" :disabled="saving">
      <div class="project-grid">
        <el-form-item v-if="!initialProject" label="所属组织" required
          ><RemoteSelect
            v-model="form.org_id"
            :load-options="getMesOrgOptions"
            placeholder="选择组织"
            auto-select-single /></el-form-item
        ><el-form-item label="项目编号" required
          ><el-input
            v-model="form.production_order_no"
            maxlength="64"
            placeholder="如：PO-20261023-001" /></el-form-item
        ><el-form-item label="项目名称" required
          ><el-input
            v-model="form.project_name"
            maxlength="128" /></el-form-item
        ><el-form-item label="客户档案"
          ><RemoteSelect
            :model-value="form.customer_id || ''"
            :context-key="form.org_id"
            :disabled="!form.org_id"
            :load-options="
              (value) => archiveOptions('customers', form.org_id, value)
            "
            :initial-option="
              form.customer_id
                ? {
                    value: form.customer_id,
                    label: form.customer_name || form.customer_no,
                  }
                : undefined
            "
            placeholder="可选，按客户代号搜索"
            @select="
              (option) => selectCustomer(option as ArchiveOption | undefined)
            "
        /></el-form-item>
        <el-form-item label="客户编号"
          ><el-input
            v-model="form.customer_no"
            :disabled="!!form.customer_id"
            maxlength="64"
            placeholder="外部客户编号（可选）" /></el-form-item
        ><el-form-item label="客户名称"
          ><el-input
            v-model="form.customer_name"
            :disabled="!!form.customer_id"
            maxlength="128"
            placeholder="客户名称（可选）" /></el-form-item
        ><el-form-item label="项目备注"
          ><el-input v-model="form.note" maxlength="4000"
        /></el-form-item>
      </div>
      <div class="section-heading">
        <strong
          >{{ purpose === "edit" ? "本次追加产品" : "产品明细" }}（{{
            products.length
          }}）</strong
        ><el-button :disabled="products.length >= 100" @click="configure()"
          >＋ 添加产品</el-button
        >
      </div>
      <el-table
        :data="products"
        max-height="360"
        empty-text="添加货品，填写数量并上传图纸；工序在保存后另行配置"
      >
        <el-table-column label="产品工单号" min-width="180"
          ><template #default="{ row, $index }">{{
            row.work_order_no ||
            `${form.production_order_no || "新项目编号"}-${String($index + 1).padStart(3, "0")}`
          }}</template></el-table-column
        ><el-table-column
          prop="product_label"
          label="产品"
          min-width="200"
        /><el-table-column
          prop="planned_quantity"
          label="计划数量"
          width="110"
        /><el-table-column label="货品类型" width="100"
          ><template #default="{ row }">{{
            mesProcessingTypeLabel(row.processing_type_code || "in_house")
          }}</template></el-table-column
        ><el-table-column label="图纸 / 模型" width="120">
          <template #default="{ row }">{{
            row.drawing_files?.length
              ? `${row.drawing_files.length} 个文件`
              : "未添加"
          }}</template> </el-table-column
        ><el-table-column label="操作" width="150"
          ><template #default="{ $index }"
            ><el-button link type="primary" @click="configure($index)"
              >编辑货品</el-button
            ><el-button link type="danger" @click="removeProduct($index)"
              >移除</el-button
            ></template
          ></el-table-column
        >
      </el-table>
      <p>
        创建时只保存工单与货品资料，状态为未配置。配置工序后变为待下单，点击列表“下单”进入生产。
      </p>
    </el-form>
    <template #footer
      ><el-button :disabled="saving" @click="visible = false">取消</el-button
      ><el-button type="primary" :loading="saving" @click="submit()">{{
        purpose === "edit" ? "保存资料及追加货品" : "创建工单与货品"
      }}</el-button></template
    >
    <WorkOrderCreate
      v-model="productVisible"
      purpose="configure"
      :org-id="form.org_id"
      :initial-order="product"
      @configured="configured"
    />
  </el-dialog>
</template>

<style scoped>
.submit-error {
  margin-bottom: 16px;
}

.project-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0 18px;
}

.section-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin: 6px 0 14px;
}

p {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

@media (width <= 760px) {
  .project-grid {
    grid-template-columns: 1fr;
  }
}
</style>
