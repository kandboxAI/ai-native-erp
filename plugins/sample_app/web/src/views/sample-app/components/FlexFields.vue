<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import {
  useSampleApi,
  type FlexField,
  type FlexValueType,
  type FlexValues,
} from "@plugins/sample_app/web/src/api/sample_app";

const props = defineProps<{ formKey: string; modelValue: FlexValues }>();
const emit = defineEmits<{
  "update:modelValue": [value: FlexValues];
  fields: [value: FlexField[]];
}>();
const { listFlexFields, createFlexField, updateFlexField } = useSampleApi();
const fields = ref<FlexField[]>([]);
const manager = ref(false);
const saving = ref(false);
const draft = reactive({
  field_name: "",
  field_key: "",
  value_type_code: "string" as FlexValueType,
  is_required: false,
});
const types = [
  { value: "string", label: "文本" },
  { value: "number", label: "数值" },
  { value: "date", label: "日期" },
  { value: "boolean", label: "是否" },
];
const active = computed(() =>
  fields.value.filter((item) => item.is_active),
);

function typeLabel(value: string) {
  return types.find((item) => item.value === value)?.label || value;
}

async function load() {
  const result = await listFlexFields(props.formKey);
  if (result.code !== 0) {
    ElMessage.error(result.message);
    return;
  }
  fields.value = result.data;
  emit("fields", result.data);
}

function setValue(key: string, value: FlexValues[string]) {
  emit("update:modelValue", { ...props.modelValue, [key]: value });
}

async function addField() {
  if (saving.value) return;
  saving.value = true;
  try {
    const result = await createFlexField({
      form_key: props.formKey,
      field_name: draft.field_name.trim(),
      field_key: draft.field_key.trim(),
      value_type_code: draft.value_type_code,
      is_required: draft.is_required,
    });
    if (result.code !== 0) {
      ElMessage.error(result.message);
      return;
    }
    draft.field_name = "";
    draft.field_key = "";
    draft.value_type_code = "string";
    draft.is_required = false;
    await load();
  } finally {
    saving.value = false;
  }
}

async function toggle(field: FlexField, activeState: boolean) {
  const result = await updateFlexField(field.id, {
    field_name: field.field_name,
    is_required: field.is_required,
    is_active: activeState,
  });
  if (result.code !== 0) {
    ElMessage.error(result.message);
    return;
  }
  await load();
}

onMounted(load);
</script>

<template>
  <el-form-item
    v-for="field in active"
    :key="field.field_key"
    :label="field.field_name"
    :required="field.is_required"
  >
    <el-input
      v-if="field.value_type_code === 'string'"
      :model-value="String(modelValue[field.field_key] ?? '')"
      maxlength="500"
      @update:model-value="setValue(field.field_key, $event)"
    />
    <el-input-number
      v-else-if="field.value_type_code === 'number'"
      :model-value="
        modelValue[field.field_key] === '' ||
        modelValue[field.field_key] == null
          ? undefined
          : Number(modelValue[field.field_key])
      "
      :precision="4"
      controls-position="right"
      class="w-full"
      @update:model-value="
        setValue(field.field_key, $event == null ? null : String($event))
      "
    />
    <el-date-picker
      v-else-if="field.value_type_code === 'date'"
      :model-value="(modelValue[field.field_key] as string) || ''"
      type="date"
      value-format="YYYY-MM-DD"
      @update:model-value="setValue(field.field_key, $event || null)"
    />
    <el-switch
      v-else
      :model-value="modelValue[field.field_key] === true"
      @update:model-value="setValue(field.field_key, $event)"
    />
  </el-form-item>
  <el-form-item label="自定义">
    <el-button link type="primary" @click="manager = true"
      >管理字段</el-button
    >
  </el-form-item>
  <el-dialog
    v-model="manager"
    title="自定义字段"
    width="640px"
    append-to-body
    :close-on-click-modal="false"
  >
    <p class="mb-3 text-sm text-gray-500">
      字段只作登记，不参与工资核算或项目毛利。标识创建后不能修改；停用后表单不再显示，已填写的值仍保留。
    </p>
    <el-table :data="fields" size="small">
      <el-table-column prop="field_name" label="名称" />
      <el-table-column prop="field_key" label="标识" />
      <el-table-column label="类型" width="80">
        <template #default="{ row }">{{
          typeLabel(row.value_type_code)
        }}</template>
      </el-table-column>
      <el-table-column label="必填" width="70">
        <template #default="{ row }">{{
          row.is_required ? "是" : "否"
        }}</template>
      </el-table-column>
      <el-table-column label="启用" width="80">
        <template #default="{ row }">
          <el-switch
            :model-value="row.is_active"
            @update:model-value="toggle(row as FlexField, $event === true)"
          />
        </template>
      </el-table-column>
    </el-table>
    <el-form label-width="80px" class="mt-4" @submit.prevent="addField">
      <el-form-item label="名称" required
        ><el-input v-model="draft.field_name" maxlength="64"
      /></el-form-item>
      <el-form-item label="标识" required
        ><el-input
          v-model="draft.field_key"
          maxlength="63"
          placeholder="小写字母开头，如 monthly_wage"
      /></el-form-item>
      <el-form-item label="类型"
        ><el-select v-model="draft.value_type_code"
          ><el-option
            v-for="item in types"
            :key="item.value"
            :label="item.label"
            :value="item.value" /></el-select
      ></el-form-item>
      <el-form-item label="必填"
        ><el-switch v-model="draft.is_required"
      /></el-form-item>
      <el-button type="primary" :loading="saving" @click="addField"
        >添加字段</el-button
      >
    </el-form>
  </el-dialog>
</template>
