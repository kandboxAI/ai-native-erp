<script setup lang="ts">
import { ref } from "vue";
import { useDept } from "./utils/hook";
import { PureTableBar } from "@/components/RePureTableBar";
import { useRenderIcon } from "@/components/ReIcon/src/hooks";

import Delete from "~icons/ep/delete";
import EditPen from "~icons/ep/edit-pen";
import Refresh from "~icons/ep/refresh";
import AddFill from "~icons/ri/add-circle-line";

defineOptions({
  name: "SystemDept"
});

const formRef = ref();
const tableRef = ref();
const {
  form,
  loading,
  columns,
  dataList,
  onSearch,
  resetForm,
  applyFilter,
  schoolOptions,
  canOrgCreate,
  canOrgUpdate,
  canOrgDelete,
  canDeptCreate,
  canDeptUpdate,
  canDeptDelete,
  toolbarSchoolParentId,
  openDeptDialog,
  openOrgDialog,
  handleDelete
} = useDept();

function onFullscreen() {
  tableRef.value.setAdaptive();
}
</script>

<template>
  <ReListPresentation>
  <div class="main list-page list-presentation-container">
    <ReListHeading title="组织架构" />
    <section class="list-query-panel">
      <el-form
        ref="formRef"
        :inline="true"
        :model="form"
        class="search-form bg-bg_color w-full pl-8 pt-3 overflow-auto list-filters"
      >
        <el-form-item label="所属学校：" prop="school_id">
          <el-select
            v-model="form.school_id"
            placeholder="请选择学校"
            clearable
            filterable
            class="w-45!"
          >
            <el-option
              v-for="school in schoolOptions"
              :key="school.id"
              :label="school.org_name"
              :value="school.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="名称：" prop="keyword">
          <el-input
            v-model="form.keyword"
            placeholder="请输入名称或编号"
            clearable
            class="w-45!"
          />
        </el-form-item>
        <el-form-item label="类型：" prop="type_code">
          <el-select
            v-model="form.type_code"
            placeholder="请选择类型"
            clearable
            class="w-45!"
          >
            <el-option label="集团" value="group" />
            <el-option label="学校" value="school" />
            <el-option label="组织" value="organization" />
            <el-option label="部门" value="department" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态：" prop="is_active">
          <el-select
            v-model="form.is_active"
            placeholder="请选择状态"
            clearable
            class="w-45!"
          >
            <el-option label="启用" :value="true" />
            <el-option label="停用" :value="false" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button
            data-list-query="search"
            type="primary"
            :icon="useRenderIcon('ri/search-line')"
            :loading="loading"
            @click="applyFilter"
          >
            搜索
          </el-button>
          <el-button
            data-list-query="reset"
            :icon="useRenderIcon(Refresh)"
            @click="resetForm(formRef)"
          >
            重置
          </el-button>
        </el-form-item>
      </el-form>

      <PureTableBar
        :list-heading="false"
        title="组织架构"
        :columns="columns"
        :tableRef="tableRef?.getTableRef()"
        @refresh="onSearch"
        @fullscreen="onFullscreen"
      >
        <template #buttons>
          <el-button
            data-list-action="create"
            v-if="canOrgCreate && toolbarSchoolParentId"
            type="primary"
            :icon="useRenderIcon(AddFill)"
            @click="
              openOrgDialog('新增', {
                parent_id: toolbarSchoolParentId,
                org_type_code: 'school'
              })
            "
          >
            新增学校
          </el-button>
        </template>
        <template v-slot="{ size, dynamicColumns }">
          <ReListTable
            list-key="index-0"
            engine="pure"
            list-local
            :list-refresh="applyFilter"
            ref="tableRef"
            adaptive
            :adaptiveConfig="{ offsetBottom: 45 }"
            align-whole="center"
            row-key="id"
            showOverflowTooltip
            table-layout="auto"
            default-expand-all
            :loading="loading"
            :size="size"
            :data="dataList"
            :columns="dynamicColumns"
            :header-cell-style="{
              background: 'var(--el-fill-color-light)',
              color: 'var(--el-text-color-primary)'
            }"
          >
            <template #operation="{ row }">
              <el-button
                data-list-action="edit"
                v-if="
                  (row.kind === 'org' && canOrgUpdate) ||
                  (row.kind === 'department' && canDeptUpdate)
                "
                class="reset-margin"
                link
                type="primary"
                :size="size"
                :icon="useRenderIcon(EditPen)"
                @click="
                  row.kind === 'org'
                    ? openOrgDialog('修改', {
                        id: row.id,
                        parent_id: row.parent_id,
                        org_type_code: row.type_code
                      })
                    : openDeptDialog('修改', row)
                "
              >
                修改
              </el-button>
              <el-button
                data-list-action="create"
                v-if="row.type_code === 'group' && canOrgCreate"
                class="reset-margin"
                link
                type="primary"
                :size="size"
                :icon="useRenderIcon(AddFill)"
                @click="
                  openOrgDialog('新增', {
                    parent_id: row.id,
                    org_type_code: 'school'
                  })
                "
              >
                新增学校
              </el-button>
              <el-button
                data-list-action="create"
                v-if="
                  (row.type_code === 'school' ||
                    row.type_code === 'organization') &&
                  canDeptCreate
                "
                class="reset-margin"
                link
                type="primary"
                :size="size"
                :icon="useRenderIcon(AddFill)"
                @click="openDeptDialog('新增', { org_id: row.id })"
              >
                新增部门
              </el-button>
              <el-button
                data-list-action="create"
                v-if="row.kind === 'department' && canDeptCreate"
                class="reset-margin"
                link
                type="primary"
                :size="size"
                :icon="useRenderIcon(AddFill)"
                @click="
                  openDeptDialog('新增', {
                    org_id: row.org_id,
                    parent_id: row.id
                  })
                "
              >
                新增下级
              </el-button>
              <el-popconfirm confirm-button-type="danger"
                v-if="
                  (row.kind === 'org' && canOrgDelete) ||
                  (row.kind === 'department' && canDeptDelete)
                "
                :title="`是否确认删除${row.type_label}「${row.name}」`"
                @confirm="handleDelete(row)"
              >
                <template #reference>
                  <el-button
                    data-list-action="delete"
                    class="reset-margin"
                    link
                    type="primary"
                    :size="size"
                    :icon="useRenderIcon(Delete)"
                  >
                    删除
                  </el-button>
                </template>
              </el-popconfirm>
            </template>
          </ReListTable>
        </template>
      </PureTableBar>
    </section>
  </div>

  </ReListPresentation>
</template>

<style lang="scss" scoped>
:deep(.el-table__inner-wrapper::before) {
  height: 0;
}

.main-content {
  margin: 24px 24px 0 !important;
}

.search-form {
  :deep(.el-form-item) {
    margin-bottom: 12px;
  }
}
</style>
