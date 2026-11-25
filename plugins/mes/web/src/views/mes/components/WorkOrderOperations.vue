<script setup lang="ts">
import draggable from "vuedraggable/src/vuedraggable";
import RemoteSelect from "./RemoteSelect.vue";
import ArchiveOperationPicker from "./ArchiveOperationPicker.vue";
import type { useWorkOrderOperations } from "../work-orders/useWorkOrderOperations";
const props = defineProps<{
  editor: ReturnType<typeof useWorkOrderOperations>;
}>();
const {
  form,
  configurationLocked,
  saving,
  manage,
  canSaveRoutes,
  unit,
  source,
  templateChoices,
  templateId,
  templateLoading,
  templateError,
  templatesLoaded,
  routeVisible,
  routeSaving,
  routeForm,
  activeOperationKey,
  operationList,
  searchTemplates,
  applyTemplate,
  openSaveRoute,
  saveCurrentRoute,
  move,
  orderChanged,
  removeOperation,
  addOperation,
} = props.editor;
</script>
<template>
  <section class="work-order-operations" aria-label="工序配置表单">
    <div class="section-heading">
      <div>
        <h3>
          生产工序
          <span class="operation-count">{{ form.operations.length }} 道</span>
        </h3>
        <p>
          拖动左侧手柄调整执行顺序，点击工序展开编辑。数量留空时沿用工单计划数量。
        </p>
      </div>
      <el-button
        :disabled="configurationLocked || form.operations.length >= 100"
        @click="addOperation"
        >＋ 添加工序</el-button
      >
    </div>
    <el-form-item label="工艺路线" class="route-field">
      <div class="template-toolbar">
        <el-select
          v-model="templateId"
          filterable
          remote
          clearable
          :remote-method="searchTemplates"
          :loading="templateLoading"
          :disabled="configurationLocked || saving || !form.org_id"
          placeholder="选择已有工艺路线"
          style="width: min(460px, 100%)"
          @visible-change="(value) => value && searchTemplates()"
        >
          <el-option
            v-if="
              form.process_template_id &&
              !templateChoices.some(
                (item) => item.id === form.process_template_id,
              )
            "
            :value="form.process_template_id"
            :label="`已应用路线 · v${form.process_template_version_snapshot}`"
            disabled
          />
          <el-option
            v-for="item in templateChoices"
            :key="item.id"
            :value="item.id"
            :disabled="item.is_product_active === false"
            :label="`${item.template_no} · ${item.template_name} · ${item.product_option?.label || (item.product_item_id ? '产品专用' : '组织通用')} · v${item.version_no}`"
          />
        </el-select>
        <el-button
          :disabled="
            configurationLocked ||
            saving ||
            templateLoading ||
            !templateId ||
            !templateChoices.some((item) => item.id === templateId)
          "
          @click="applyTemplate"
          >应用路线并生成工序</el-button
        >
        <el-button
          v-if="canSaveRoutes"
          :disabled="
            configurationLocked ||
            saving ||
            routeSaving ||
            !form.org_id ||
            !form.operations.length
          "
          @click="openSaveRoute"
          >当前工序另存为路线</el-button
        >
        <small v-if="form.process_template_id"
          >已应用路线修订
          {{
            form.process_template_version_snapshot
          }}；可按本单调整，路线更新不影响本单。</small
        >
      </div>
      <el-alert
        v-if="templateError"
        :title="templateError"
        type="error"
        :closable="false"
      />
      <small v-else-if="templatesLoaded && !templateChoices.length"
        >未找到适用的启用路线，可更换关键词，或把当前工序另存为路线。</small
      >
      <small v-else-if="!configurationLocked"
        >可选用当前货品专用或同组织通用路线，也可手工添加工序。</small
      >
    </el-form-item>
    <div
      ref="operationList"
      class="operation-list"
      role="region"
      aria-label="生产工序列表"
    >
      <draggable
        v-model="form.operations"
        item-key="key"
        handle=".operation-drag-handle"
        :animation="180"
        :disabled="saving || configurationLocked"
        ghost-class="operation-sort-ghost"
        drag-class="operation-sort-drag"
        @change="orderChanged"
      >
        <template #item="{ element: row, index }">
          <div
            class="operation-card"
            :class="{ expanded: activeOperationKey === row.key }"
            :data-operation-key="row.key"
          >
            <div class="operation-heading">
              <button
                type="button"
                class="operation-drag-handle"
                :disabled="saving || configurationLocked"
                :aria-label="`拖动第${index + 1}道工序调整顺序`"
                title="拖动调整顺序"
              >
                ⠿
              </button>
              <button
                type="button"
                class="operation-toggle"
                :aria-expanded="activeOperationKey === row.key"
                :aria-controls="`operation-editor-${row.key}`"
                @click="
                  activeOperationKey =
                    activeOperationKey === row.key ? undefined : row.key
                "
              >
                <span class="sequence">{{ index + 1 }}</span>
                <span class="operation-summary"
                  ><strong>{{ row.operation_name || "新工序" }}</strong>
                  <el-tag
                    v-if="
                      !row.process_id &&
                      row.operation_description?.includes('工艺档案待匹配：')
                    "
                    type="warning"
                    size="small"
                    >待匹配工艺</el-tag
                  >
                  ><small
                    >工序号 {{ row.operation_no || "未填写" }} · 计划
                    {{ row.planned_quantity ?? form.planned_quantity }}
                    {{ unit
                    }}{{
                      row.work_center_name ? ` · ${row.work_center_name}` : ""
                    }}</small
                  ></span
                >
                <span class="expand-label">{{
                  activeOperationKey === row.key ? "收起 ▴" : "编辑 ▾"
                }}</span>
              </button>
              <div class="operation-actions">
                <el-button
                  text
                  :disabled="saving || configurationLocked || index === 0"
                  :aria-label="`上移第${index + 1}道工序`"
                  @click="move(index, -1)"
                  >上移</el-button
                ><el-button
                  text
                  :disabled="
                    saving ||
                    configurationLocked ||
                    index === form.operations.length - 1
                  "
                  :aria-label="`下移第${index + 1}道工序`"
                  @click="move(index, 1)"
                  >下移</el-button
                ><el-button
                  text
                  type="danger"
                  :disabled="saving || configurationLocked"
                  @click="removeOperation(index)"
                  >删除</el-button
                >
              </div>
            </div>
            <div
              v-show="activeOperationKey === row.key"
              :id="`operation-editor-${row.key}`"
              class="operation-editor"
            >
              <fieldset
                :disabled="configurationLocked"
                class="operation-fields"
              >
                <ArchiveOperationPicker
                  :org-id="form.org_id"
                  :model-value="row"
                  :load-options="source.loadArchives"
                  :disabled="configurationLocked"
                  @update:model-value="(value) => Object.assign(row, value)"
                />
                <div class="operation-grid">
                  <el-form-item
                    label="工序号"
                    :prop="`operations.${index}.operation_no`"
                    :rules="[
                      {
                        required: true,
                        whitespace: true,
                        message: '请填写工序号',
                        trigger: 'blur',
                      },
                    ]"
                    ><el-input v-model="row.operation_no" maxlength="64"
                  /></el-form-item>
                  <el-form-item
                    label="工序名称"
                    :prop="`operations.${index}.operation_name`"
                    :rules="[
                      {
                        required: true,
                        whitespace: true,
                        message: '请填写工序名称',
                        trigger: 'blur',
                      },
                    ]"
                    ><el-input
                      v-model="row.operation_name"
                      :disabled="!!row.process_id"
                      maxlength="128"
                      placeholder="如：下料 / CNC / 装配"
                  /></el-form-item>
                  <el-form-item label="计划数量（可选）"
                    ><el-input-number
                      v-model="row.planned_quantity"
                      :min="0.001"
                      :precision="3"
                      :controls="false"
                      :placeholder="String(form.planned_quantity)"
                  /></el-form-item>
                  <el-form-item label="单件预计工时（小时）"
                    ><el-input-number
                      :model-value="
                        row.standard_minutes_per_unit == null
                          ? undefined
                          : row.standard_minutes_per_unit / 60
                      "
                      :min="0.001"
                      :max="87600"
                      :precision="3"
                      :controls="false"
                      placeholder="填写每件耗时"
                      @update:model-value="
                        (value) =>
                          (row.standard_minutes_per_unit =
                            value == null
                              ? undefined
                              : Number((value * 60).toFixed(3)))
                      "
                    />
                    <small v-if="row.standard_minutes_per_unit != null"
                      >按
                      {{ row.planned_quantity ?? form.planned_quantity }}
                      {{ unit || "件" }}，预计共
                      {{
                        Number(
                          (
                            (row.standard_minutes_per_unit *
                              (row.planned_quantity ?? form.planned_quantity)) /
                            60
                          ).toFixed(3),
                        )
                      }}
                      小时</small
                    >
                  </el-form-item>
                  <el-form-item label="工作中心"
                    ><el-input
                      v-model="row.work_center_name"
                      maxlength="128"
                      placeholder="如：机加工车间"
                  /></el-form-item>
                  <el-form-item label="工作站"
                    ><el-input
                      v-model="row.workstation_name"
                      maxlength="128"
                      placeholder="如：CNC-01"
                  /></el-form-item>
                  <el-form-item label="报工账号（可选）"
                    ><RemoteSelect
                      v-model="row.assigned_user_id"
                      :disabled="configurationLocked || !form.org_id"
                      :initial-option="
                        row.assigned_user_id && row.assigned_user_name
                          ? {
                              value: row.assigned_user_id,
                              label: row.assigned_user_name,
                            }
                          : undefined
                      "
                      :context-key="form.org_id"
                      :load-options="
                        (keyword) =>
                          source.loadAssignees(
                            keyword,
                            form.org_id,
                            manage,
                          )
                      "
                      placeholder="选择组织后按姓名查找"
                      @select="
                        (option) =>
                          (row.assigned_user_name = option?.label || '')
                      "
                  /></el-form-item>
                </div>
                <el-form-item label="工艺说明"
                  ><el-input
                    v-model="row.operation_description"
                    type="textarea"
                    :rows="2"
                    maxlength="4000"
                    placeholder="填写本工序的操作要求"
                /></el-form-item>
              </fieldset>
            </div>
          </div>
        </template>
      </draggable>
    </div>
    <el-dialog
      v-model="routeVisible"
      title="当前工序另存为工艺路线"
      width="min(560px, 94vw)"
      append-to-body
      :close-on-click-modal="!routeSaving"
      :close-on-press-escape="!routeSaving"
      :show-close="!routeSaving"
    >
      <el-form label-position="top" @submit.prevent="saveCurrentRoute">
        <el-form-item label="路线编号" required
          ><el-input
            v-model="routeForm.template_no"
            maxlength="64"
            :disabled="routeSaving"
            placeholder="同组织内唯一"
        /></el-form-item>
        <el-form-item label="路线名称" required
          ><el-input
            v-model="routeForm.template_name"
            maxlength="128"
            :disabled="routeSaving"
        /></el-form-item>
        <el-form-item label="适用范围"
          ><el-radio-group v-model="routeForm.scope" :disabled="routeSaving"
            ><el-radio value="product" :disabled="!form.product_item_id"
              >当前产品专用</el-radio
            ><el-radio value="general">组织通用</el-radio></el-radio-group
          ></el-form-item
        >
        <p>
          保存当前
          {{ form.operations.length }}
          道工序的顺序、工艺、设备、要求及单件工时，不包含本单计划数量和派工人员。新路线立即启用。
        </p>
      </el-form>
      <template #footer
        ><el-button :disabled="routeSaving" @click="routeVisible = false"
          >取消</el-button
        ><el-button
          type="primary"
          :loading="routeSaving"
          @click="saveCurrentRoute"
          >保存工艺路线</el-button
        ></template
      >
    </el-dialog>
  </section>
</template>
<style scoped>
.template-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
  width: 100%;
  margin: 12px 0;
}

.route-field :deep(.el-form-item__content) {
  display: block;
  min-width: 0;
}

.operation-fields {
  min-width: 0;
  padding: 0;
  margin: 0;
  border: 0;
}

.operation-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0 20px;
}

.el-input-number {
  width: 100%;
}

.section-heading,
.operation-heading {
  display: flex;
  gap: 16px;
  align-items: center;
  justify-content: space-between;
}

.section-heading {
  margin: 12px 0 16px;
}

h3 {
  margin: 0 0 6px;
  font-size: 16px;
}

p {
  margin: 0;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.operation-card {
  margin-bottom: 10px;
  background: var(--el-fill-color-blank);
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
}

.operation-card.expanded {
  border-color: var(--el-color-primary-light-5);
}

.operation-list {
  max-height: min(460px, 45dvh);
  padding: 2px 8px 2px 2px;
  overflow-y: auto;
  scrollbar-gutter: stable;
  overscroll-behavior: contain;
}

.operation-heading {
  gap: 8px;
  padding: 10px 12px;
}

.operation-toggle {
  display: flex;
  flex: 1;
  align-items: center;
  min-width: 0;
  padding: 0;
  color: inherit;
  text-align: left;
  cursor: pointer;
  background: transparent;
  border: 0;
}

.operation-toggle:focus-visible,
.operation-drag-handle:focus-visible {
  outline: 2px solid var(--el-color-primary);
  outline-offset: 3px;
  border-radius: 4px;
}

.operation-summary {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 5px;
  min-width: 0;
}

.operation-summary strong,
.operation-summary small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.operation-summary small,
.expand-label,
.operation-count {
  font-size: 12px;
  font-weight: normal;
  color: var(--el-text-color-secondary);
}

.expand-label {
  flex-shrink: 0;
  margin: 0 10px;
}

.operation-actions {
  flex-shrink: 0;
}

.operation-drag-handle {
  flex-shrink: 0;
  padding: 4px;
  font-size: 24px;
  line-height: 1;
  color: var(--el-text-color-placeholder);
  touch-action: none;
  cursor: grab;
  background: transparent;
  border: 0;
}

.operation-drag-handle:active {
  cursor: grabbing;
}

.operation-drag-handle:disabled {
  cursor: not-allowed;
}

.operation-sort-ghost {
  background: var(--el-color-primary-light-9);
  border-color: var(--el-color-primary);
  opacity: 0.4;
}

.operation-sort-drag {
  box-shadow: var(--el-box-shadow-light);
}

.operation-editor {
  padding: 16px 20px 0;
  border-top: 1px solid var(--el-border-color-lighter);
}

.sequence {
  display: inline-flex;
  flex-shrink: 0;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  margin-right: 8px;
  color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
  border-radius: 6px;
}

@media (width <= 760px) {
  .operation-grid {
    grid-template-columns: 1fr;
  }

  .section-heading {
    align-items: flex-start;
  }

  .operation-heading {
    flex-wrap: wrap;
  }

  .operation-toggle {
    flex-basis: calc(100% - 40px);
  }

  .operation-actions {
    margin-left: auto;
  }
}
</style>
