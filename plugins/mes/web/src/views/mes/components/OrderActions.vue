<script setup lang="ts">
import { hasPerms } from "@/utils/auth";
defineProps<{ order: Record<string, any>; disabled?: boolean }>();
const emit = defineEmits<{
  command: [action: string, row: Record<string, any>];
}>();
</script>
<template>
  <div class="order-actions">
    <el-button
      link
      type="primary"
      :disabled="disabled"
      @click="emit('command', 'detail', order)"
      >详情</el-button
    >
    <el-button
      v-if="hasPerms('mes:work_order:manage') && order.status_code === 'draft'"
      link
      type="primary"
      :disabled="disabled || !order.operation_count"
      :title="
        !order.operation_count
          ? '请先配置工序，再下单'
          : '下单后进入生产，数量和库存不变'
      "
      @click="emit('command', 'place', order)"
      >下单</el-button
    >
    <el-button
      v-if="order.is_process_change_pending"
      link
      type="primary"
      :disabled="disabled"
      @click="emit('command', 'process_changes', order)"
      >处理工艺变更</el-button
    >
    <el-button
      v-else-if="
        hasPerms('mes:work_order:manage') &&
        !['completed', 'cancelled'].includes(order.status_code)
      "
      link
      type="primary"
      :disabled="disabled"
      @click="
        emit(
          'command',
          ['draft', 'released'].includes(order.status_code)
            ? 'configure_operations'
            : 'edit',
          order,
        )
      "
      >{{
        ["draft", "released"].includes(order.status_code) ? "配置工序" : "变更"
      }}</el-button
    >
    <el-dropdown
      trigger="click"
      :disabled="disabled"
      @command="(action) => emit('command', action, order)"
      ><el-button link type="primary" :disabled="disabled">更多 ▾</el-button
      ><template #dropdown
        ><el-dropdown-menu>
          <el-dropdown-item v-if="!order.is_process_change_pending && order.status_code !== 'draft'" command="process_changes">工艺变更</el-dropdown-item>
          <el-dropdown-item
            v-if="
              hasPerms('mes:work_order:manage') &&
              ['draft', 'released'].includes(order.status_code)
            "
            command="edit"
            >修改货品资料</el-dropdown-item
          >
          <el-dropdown-item
            v-if="hasPerms('mes:work_order:create')"
            command="copy"
            >复制工单</el-dropdown-item
          >
          <el-dropdown-item command="print">在线打印工单卡</el-dropdown-item
          ><el-dropdown-item command="download"
            >下载工单卡（HTML）</el-dropdown-item
          >
          <el-dropdown-item
            v-if="
              hasPerms('mes:work_order:manage') &&
              ['released', 'in_progress'].includes(order.status_code)
            "
            divided
            command="pause"
            >暂停生产</el-dropdown-item
          >
          <el-dropdown-item
            v-if="
              hasPerms('mes:work_order:manage') &&
              order.status_code === 'paused' &&
              !order.is_process_change_pending
            "
            command="resume"
            >恢复生产</el-dropdown-item
          >
          <el-dropdown-item
            v-if="
              hasPerms('mes:work_order:manage') &&
              order.status_code === 'released'
            "
            command="withdraw"
            >撤回下单</el-dropdown-item
          >
          <el-dropdown-item
            v-if="
              hasPerms('mes:work_order:manage') &&
              ['released', 'in_progress'].includes(order.status_code)
            "
            command="complete"
            >完结工单</el-dropdown-item
          >
          <el-dropdown-item
            v-if="
              hasPerms('mes:work_order:manage') &&
              ['draft', 'released'].includes(order.status_code)
            "
            command="cancel"
            >取消工单</el-dropdown-item
          >
          <el-dropdown-item
            v-if="
              hasPerms('mes:work_order:manage') &&
              ['draft', 'cancelled'].includes(order.status_code)
            "
            command="delete"
            >删除未执行工单</el-dropdown-item
          >
          <el-dropdown-item
            v-if="
              hasPerms('mes:work_order:create') &&
              !['draft', 'cancelled'].includes(order.status_code)
            "
            divided
            command="repair"
            >生成返修工单</el-dropdown-item
          >
        </el-dropdown-menu></template
      ></el-dropdown
    >
  </div>
</template>
<style scoped>
.order-actions {
  display: flex;
  gap: 10px;
  align-items: center;
  white-space: nowrap;
}

.order-actions .el-button + .el-button {
  margin-left: 0;
}
</style>
