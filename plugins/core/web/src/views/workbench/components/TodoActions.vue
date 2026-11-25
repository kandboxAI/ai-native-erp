<script setup lang="ts">
import { ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { actOnTodo, getTodo, type TodoRow, type TodoAction } from "@/api/todo";
import { getHttpErrorMessage } from "@/utils/http";
import { openTodoTarget } from "@/utils/todoTarget";

const props = defineProps<{ item: TodoRow }>();
const emit = defineEmits<{ changed: [] }>();
const router = useRouter();
const busy = ref(false);
async function act(action: TodoAction) {
  if (busy.value) return;
  let comment = "";
  try {
    if (action.input) {
      const result = await ElMessageBox.prompt(
        "请填写跟进情况或完成原因",
        action.label,
        {
          inputType: "textarea",
          inputValidator: value => !!value?.trim() || "请填写内容"
        }
      );
      comment = result.value.trim();
    } else {
      const analysisNote = props.item.ai_analysis ? "AI 分析仅供参考。" : "";
      await ElMessageBox.confirm(
        `确认${action.label}“${props.item.title}”？${analysisNote}`,
        action.label
      );
    }
  } catch {
    return;
  }
  busy.value = true;
  try {
    await actOnTodo(props.item.id, action.key, comment);
    ElMessage.success(
      action.key === "retry_analysis" ? "已提交重新分析" : "已保存办理结果"
    );
    emit("changed");
  } catch (error) {
    ElMessage.error(getHttpErrorMessage(error, "办理失败，请刷新后重试"));
  } finally {
    busy.value = false;
  }
}
async function open() {
  try {
    if (props.item.is_projection) {
      if (props.item.path) await router.push(props.item.path);
      return;
    }
    const result = await getTodo(props.item.id);
    await openTodoTarget(router, result.data);
  } catch (error) {
    ElMessage.error(getHttpErrorMessage(error, "当前无法打开该待办"));
  }
}
</script>

<template>
  <div class="task-actions">
    <el-button
      v-for="action in item.actions"
      :key="action.key"
      type="primary"
      :loading="busy"
      :disabled="busy"
      @click="act(action)"
      >{{ action.label }}</el-button
    >
    <el-button
      v-if="item.targets?.web || item.path"
      type="primary"
      plain
      @click="open"
      >查看详情</el-button
    >
    <span
      v-else-if="item.web_unavailable_reason"
      class="text-sm text-(--el-text-color-secondary)"
    >
      {{ item.web_unavailable_reason }}
    </span>
  </div>
</template>
