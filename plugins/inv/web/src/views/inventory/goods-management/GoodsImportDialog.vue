<template>
  <ExcelImportDialog
    v-model="visible"
    :title="config.title"
    :notice="config.notice"
    :upload-placeholder="config.uploadPlaceholder"
    :template-file-name="config.templateFileName"
    :confirm-message="config.confirmMessage"
    :success-message="config.successMessage"
    :summary-items="config.summaryItems"
    :download-template="downloadTemplate"
    :validate-import="validateImport"
    :execute-import="executeImport"
    @success="result => emit('success', result)"
  />
</template>

<script setup lang="ts">
import { computed } from "vue";
import ExcelImportDialog from "@plugins/inv/web/src/views/inventory/shared/components/ExcelImportDialog/index.vue";
import type {
  ExcelImportResponse,
  ExcelImportSummaryItem,
  ExcelImportValidation
} from "@plugins/inv/web/src/views/inventory/shared/components/ExcelImportDialog/types";
import {
  downloadGoodsImportTemplate,
  executeGoodsImport,
  validateGoodsImport,
  type GoodsImportKind
} from "@plugins/inv/web/src/api/invGoodsImport";

const props = defineProps<{ modelValue: boolean; kind: GoodsImportKind }>();
const emit = defineEmits<{
  "update:modelValue": [value: boolean];
  success: [result: ExcelImportValidation];
}>();

const visible = computed({
  get: () => props.modelValue,
  set: value => emit("update:modelValue", value)
});

type DialogConfig = {
  title: string;
  notice: string;
  uploadPlaceholder: string;
  templateFileName: string;
  confirmMessage: string;
  successMessage: string;
  summaryItems: ExcelImportSummaryItem[];
};

const configs: Record<GoodsImportKind, DialogConfig> = {
  category: {
    title: "导入物料分类",
    notice:
      "一行代表一个物料分类。默认不覆盖同名分类，正式导入会整批提交或回滚。",
    uploadPlaceholder: "点击选择或拖入物料分类导入模板",
    templateFileName: "物料分类导入模板",
    confirmMessage: "确认写入本批物料分类？",
    successMessage: "物料分类导入完成",
    summaryItems: [
      { label: "数据行", key: "rows" },
      { label: "物料分类", key: "categories" }
    ]
  },
  product: {
    title: "导入物料档案",
    notice:
      "填写编号时按编号匹配；编号留空按名称+规格匹配，新增自动生成编号。可选项留空将清空原值；更新已有物料需开启允许更新。分类、单位和供应商从模板下拉选择。",
    uploadPlaceholder: "点击选择或拖入物料档案导入模板",
    templateFileName: "物料档案导入模板",
    confirmMessage: "确认写入本批物料档案？",
    successMessage: "物料档案导入完成",
    summaryItems: [
      { label: "数据行", key: "rows" },
      { label: "物料", key: "items" }
    ]
  },
  stock: {
    title: "导入库存盘点",
    notice:
      "模板数量是盘点后的实际库存，不是增加数量。系统按仓库生成“盘点调整”单据并确认，按实盘数与账面数的差额记库存流水；已有非零库存需开启允许更新。",
    uploadPlaceholder: "点击选择或拖入库存盘点导入模板",
    templateFileName: "库存盘点导入模板",
    confirmMessage: "确认按实盘数量生成盘点调整单据并记账？",
    successMessage: "库存盘点导入完成",
    summaryItems: [
      { label: "数据行", key: "rows" },
      { label: "仓库", key: "warehouses" },
      { label: "物料", key: "items" }
    ]
  }
};

const config = computed(() => configs[props.kind]);
const downloadTemplate = () => downloadGoodsImportTemplate(props.kind);
const validateImport = (file: File, allowUpdateExisting: boolean) =>
  validateGoodsImport(
    props.kind,
    file,
    allowUpdateExisting
  ) as Promise<ExcelImportResponse>;
const executeImport = (file: File, allowUpdateExisting: boolean) =>
  executeGoodsImport(
    props.kind,
    file,
    allowUpdateExisting
  ) as Promise<ExcelImportResponse>;
</script>
