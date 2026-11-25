<template>
  <div v-if="items.length" class="order-items">
    <div class="order-items-lines">
      <div v-for="item in visibleItems" :key="item.line_no" class="order-item">
        <span class="order-item-name" :title="item.item_name">{{
          item.item_name
        }}</span>
        <span class="order-item-quantity">
          {{ formatQuantity(item.quantity) }}
          {{ unitLabel(item.unit_code) || "单位缺失" }}
        </span>
      </div>
    </div>
    <el-popover
      v-if="items.length > 2"
      v-model:visible="detailVisible"
      trigger="click"
      placement="bottom-start"
      :width="420"
      :show-arrow="false"
      popper-style="padding: 0; max-width: calc(100vw - 32px)"
    >
      <template #reference>
        <button
          type="button"
          class="order-items-toggle"
          :aria-expanded="detailVisible"
          :aria-label="`查看全部 ${items.length} 行物料明细`"
        >
          <span class="order-items-count">共 {{ items.length }} 项</span>
          <span class="order-items-link">查看明细</span>
          <svg viewBox="0 0 16 16" width="12" height="12" aria-hidden="true">
            <path
              d="m6 4 4 4-4 4"
              fill="none"
              stroke="currentColor"
              stroke-width="1.5"
              stroke-linecap="round"
              stroke-linejoin="round"
            />
          </svg>
        </button>
      </template>
      <section class="order-items-detail">
        <header class="order-items-detail-heading">
          <span>物料明细</span>
          <span class="order-items-count">共 {{ items.length }} 项</span>
        </header>
        <el-scrollbar max-height="320px">
          <table class="order-items-detail-table">
            <thead>
              <tr>
                <th scope="col">物料</th>
                <th scope="col">数量 / 单位</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in items" :key="item.line_no">
                <td>{{ item.item_name }}</td>
                <td>
                  {{ formatQuantity(item.quantity) }}
                  {{ unitLabel(item.unit_code) || "单位缺失" }}
                </td>
              </tr>
            </tbody>
          </table>
        </el-scrollbar>
      </section>
    </el-popover>
  </div>
  <span v-else>—</span>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import { formatQuantity } from "@/utils/quantity";
import type { StockOrderItemSummary } from "@plugins/inv/web/src/api/inventoryManagement";

const props = defineProps<{
  items: StockOrderItemSummary[];
  unitLabel: (code: string) => string;
}>();

const detailVisible = ref(false);
const visibleItems = computed(() => props.items.slice(0, 2));
</script>

<style scoped lang="scss">
.order-items {
  max-width: 280px;
  padding: 2px 0;
}

.order-items-lines {
  display: grid;
  grid-template-columns: minmax(0, max-content) max-content;
  gap: 6px 12px;
  align-items: center;
  justify-content: start;
  line-height: 20px;
}

.order-item {
  display: contents;
}

.order-item-name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.order-item-quantity {
  justify-self: start;
  padding: 0 6px;
  color: var(--el-text-color-regular);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
  background: var(--el-fill-color-light);
  border-radius: 4px;
}

.order-items-toggle {
  display: inline-flex;
  gap: 6px;
  align-items: center;
  padding: 0;
  margin-top: 6px;
  font: inherit;
  font-size: 12px;
  line-height: 18px;
  color: var(--el-color-primary);
  cursor: pointer;
  background: transparent;
  border: 0;

  &:hover .order-items-link {
    text-decoration: underline;
  }

  &:focus-visible {
    outline: 2px solid var(--el-color-primary);
    outline-offset: 2px;
  }
}

.order-items-count {
  font-size: 12px;
  font-weight: normal;
  color: var(--el-text-color-secondary);
}

.order-items-link {
  padding-left: 8px;
  border-left: 1px solid var(--el-border-color);
}

.order-items-detail {
  color: var(--el-text-color-regular);
}

.order-items-detail-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.order-items-detail-table {
  width: 100%;
  font-size: 13px;
  line-height: 20px;
  border-spacing: 0;

  th,
  td {
    padding: 9px 16px;
    text-align: left;
    border-bottom: 1px solid var(--el-border-color-lighter);
  }

  th {
    position: sticky;
    top: 0;
    z-index: 1;
    font-size: 12px;
    font-weight: normal;
    color: var(--el-text-color-secondary);
    background: var(--el-fill-color-light);
  }

  td:first-child {
    overflow-wrap: anywhere;
  }

  th:last-child,
  td:last-child {
    text-align: right;
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
  }

  tr:last-child td {
    border-bottom: 0;
  }
}
</style>
