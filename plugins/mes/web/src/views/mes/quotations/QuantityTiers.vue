<script setup lang="ts">
import type { QuoteLine } from "./api";
const props = defineProps<{
  line: QuoteLine;
  business: boolean;
  price: boolean;
  review?: boolean;
  original?: QuoteLine;
  currency: string;
}>();
const emit = defineEmits<{
  update: [tiers: NonNullable<QuoteLine["quantity_tiers"]>];
}>();
function add() {
  const tiers = props.line.quantity_tiers || [];
  const used = new Set([
    props.line.quantity,
    ...tiers.map((tier) => tier.quantity),
  ]);
  let quantity =
    props.line.quantity < 1000000
      ? Number(Math.min(1000000, props.line.quantity + 1).toFixed(3))
      : 1;
  while (used.has(quantity))
    quantity =
      quantity < 1000000
        ? Number(Math.min(1000000, quantity + 1).toFixed(3))
        : 1;
  if (tiers.length < 4)
    emit("update", [
      ...tiers,
      {
        quantity,
        unit_price: null,
        calculation_note: "",
      },
    ]);
}
function remove(index: number) {
  emit(
    "update",
    (props.line.quantity_tiers || []).filter((_, i) => i !== index),
  );
}
function change(
  index: number,
  value: Partial<NonNullable<QuoteLine["quantity_tiers"]>[number]>,
) {
  emit(
    "update",
    (props.line.quantity_tiers || []).map((tier, i) =>
      i === index ? { ...tier, ...value } : tier,
    ),
  );
}
</script>
<template>
  <el-popover placement="bottom" :width="560" trigger="click">
    <template #reference
      ><el-button link type="primary"
        >数量报价（{{ 1 + (line.quantity_tiers?.length || 0) }} 档）</el-button
      ></template
    >
    <p>
      主数量 {{ line.quantity }} {{ line.unit_name }}，单价
      {{ line.unit_price ?? "未报价" }} {{ currency }}；交期由审批人统一确认。
    </p>
    <el-table :data="line.quantity_tiers || []" max-height="320" border>
      <el-table-column label="额外数量" width="155"
        ><template #default="{ row, $index }"
          ><el-input-number
            :model-value="row.quantity"
            :disabled="!business"
            :min="0.001"
            :max="1000000"
            :precision="3"
            controls-position="right"
            @update:model-value="
              (value) => change($index, { quantity: value })
            " /></template
      ></el-table-column>
      <el-table-column label="本档单价" width="155"
        ><template #default="{ row, $index }"
          ><el-input-number
            :model-value="row.unit_price"
            :disabled="!(price || review)"
            :min="0"
            :max="100000000"
            :precision="2"
            controls-position="right"
            @update:model-value="
              (value) => change($index, { unit_price: value })
            "
          /><small v-if="review"
            >工程原价：{{
              original?.quantity_tiers?.find((tier) => tier.id === row.id)
                ?.unit_price ?? "未报价"
            }}
            {{ currency }}</small
          ></template
        ></el-table-column
      >
      <el-table-column label="核算依据" min-width="150"
        ><template #default="{ row, $index }"
          ><el-input
            :model-value="row.calculation_note"
            :disabled="!price"
            maxlength="1000"
            placeholder="本数量档人工核算说明"
            @update:model-value="
              (value) => change($index, { calculation_note: value })
            " /></template
      ></el-table-column>
      <el-table-column v-if="business" label="操作" width="65"
        ><template #default="{ $index }"
          ><el-button link type="danger" @click="remove($index)"
            >移除</el-button
          ></template
        ></el-table-column
      >
    </el-table>
    <el-button
      v-if="business"
      :disabled="(line.quantity_tiers?.length || 0) >= 4"
      @click="add"
      >添加数量档（最多五档）</el-button
    >
    <p v-if="price">AI 采用仅回填主数量单价；其他数量档需独立人工核算。</p>
  </el-popover>
</template>
