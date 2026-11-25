<script setup lang="ts">
import { actionMessage } from "@/utils/message";
import { ref } from "vue";
import {
  mergeProductDrawingSelection,
  type ProductDrawing,
} from "../work-orders/productDrawings";
const props = defineProps<{ disabled?: boolean }>();
const files = defineModel<ProductDrawing[]>({ default: () => [] });
const emit = defineEmits<{ removed: [file: ProductDrawing] }>();
const dragging = ref(false);
function select(event: Event) {
  const input = event.target as HTMLInputElement;
  const incoming = Array.from(input.files || []);
  input.value = "";
  applySelection(incoming);
}
function drop(event: DragEvent) {
  dragging.value = false;
  applySelection(Array.from(event.dataTransfer?.files || []));
}
function applySelection(incoming: File[]) {
  if (props.disabled || !incoming.length) return;
  try {
    const selected = mergeProductDrawingSelection(incoming, files.value);
    files.value
      .filter((row) => !selected.includes(row))
      .forEach((file) => emit("removed", file));
    files.value = selected;
  } catch (cause) {
    actionMessage((cause as Error).message);
  }
}
function remove(file: ProductDrawing) {
  if (props.disabled) return;
  files.value = files.value.filter((row) => row !== file);
  emit("removed", file);
}
</script>
<template>
  <section class="product-drawings">
    <label
      class="drawing-picker"
      :class="{ disabled, dragging }"
      @dragover.prevent="dragging = !disabled"
      @dragleave.prevent="dragging = false"
      @drop.prevent="drop"
    >
      <svg
        width="28"
        height="28"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="1.5"
        aria-hidden="true"
      >
        <path
          d="M12 16V4m-4 4 4-4 4 4M4 15v4a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-4"
        />
      </svg>
      <strong>点击选择或拖入图纸与模型</strong>
      <span>可一次同时选择 PDF 和 STP / STEP，自动识别类型</span>
      <input
        type="file"
        multiple
        accept=".pdf,.stp,.step"
        :disabled="disabled"
        aria-label="选择图纸与模型"
        @change="select"
      />
    </label>
    <div class="drawing-list">
      <div
        v-for="(file, index) in files"
        :key="file.id || index"
        class="selected-drawing"
      >
        <el-tag
          size="small"
          :type="file.kind === 'pdf' ? 'primary' : 'success'"
          >{{ file.kind === "pdf" ? "二维图纸" : "三维模型" }}</el-tag
        >
        <span :title="file.name">{{ file.name }}</span
        ><small>{{ (file.size / 1024 / 1024).toFixed(2) }} MB</small>
        <el-button link type="danger" :disabled="disabled" @click="remove(file)"
          >移除</el-button
        >
      </div>
    </div>
    <p class="drawing-note">
      每类最多一份，可只选其一，单文件不超过20MB。重新选择会替换同类文件，随工单创建一并提交。
    </p>
  </section>
</template>
<style scoped>
.drawing-picker {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 8px;
  align-items: center;
  padding: 22px 16px;
  overflow: hidden;
  color: var(--el-color-primary);
  cursor: pointer;
  background: var(--el-fill-color-lighter);
  border: 1px dashed var(--el-border-color);
  border-radius: 8px;
}

.drawing-picker.dragging,
.drawing-picker:not(.disabled):hover,
.drawing-picker:focus-within {
  background: var(--el-color-primary-light-9);
  border-color: var(--el-color-primary);
}

.drawing-picker strong {
  font-size: 14px;
}

.drawing-picker > span {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.drawing-list {
  margin-top: 10px;
}

.drawing-picker input {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  cursor: pointer;
  opacity: 0;
}

.drawing-picker.disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.selected-drawing {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 5px 0;
}

.selected-drawing > span:not(.el-tag) {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.drawing-note,
.selected-drawing small {
  font-size: 12px;
  line-height: 1.6;
  color: var(--el-text-color-secondary);
}
</style>
