<script setup lang="ts">
import { ref } from "vue";
import { useMenu } from "./utils/hook";
import { PureTableBar } from "@/components/RePureTableBar";
import { useRenderIcon } from "@/components/ReIcon/src/hooks";

import Delete from "~icons/ep/delete";
import EditPen from "~icons/ep/edit-pen";
import Refresh from "~icons/ep/refresh";
import AddFill from "~icons/ri/add-circle-line";

defineOptions({
  name: "SystemMenu"
});

const formRef = ref();
const tableRef = ref();
const {
  form,
  loading,
  columns,
  dataList,
  menuView,
  isStoredMenu,
  onSearch,
  resetForm,
  openDialog,
  handleDelete,
  handleSelectionChange
} = useMenu();

function onFullscreen() {
  // 重置表格高度
  tableRef.value.setAdaptive();
}
</script>

<template>
  <ReListPresentation>
  <div class="main list-page list-presentation-container">
    <ReListHeading title="菜单管理" />
    <section class="list-query-panel">
      <el-form
        ref="formRef"
        :inline="true"
        :model="form"
        class="search-form bg-bg_color w-full pl-8 pt-3 overflow-auto list-filters"
      >
        <el-form-item label="菜单名称：" prop="menu_name">
          <el-input
            v-model="form.menu_name"
            placeholder="请输入菜单名称"
            clearable
            class="w-45!"
          />
        </el-form-item>
        <el-form-item>
          <el-button
            data-list-query="search"
            type="primary"
            :icon="useRenderIcon('ri/search-line')"
            :loading="loading"
            @click="onSearch"
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
        title="菜单管理"
        :columns="columns"
        :isExpandAll="true"
        :tableRef="tableRef?.getTableRef()"
        @refresh="onSearch"
        @fullscreen="onFullscreen"
      >
        <template #buttons>
          <el-radio-group v-model="menuView" aria-label="菜单结构">
            <el-radio-button value="sidebar">侧栏结构</el-radio-button>
            <el-radio-button value="directory">原始目录</el-radio-button>
          </el-radio-group>
          <el-button
            data-list-action="create"
            type="primary"
            :icon="useRenderIcon(AddFill)"
            @click="openDialog()"
          >
            新增菜单
          </el-button>
        </template>
        <template v-slot="{ size, dynamicColumns }">
          <ReListTable
            list-key="index-0"
            engine="pure"
            list-local
            :list-refresh="onSearch"
            ref="tableRef"
            adaptive
            :adaptiveConfig="{ offsetBottom: 45 }"
            align-whole="center"
            row-key="id"
            showOverflowTooltip
            table-layout="auto"
            :loading="loading"
            :size="size"
            :data="dataList"
            :columns="dynamicColumns"
            :header-cell-style="{
              background: 'var(--el-fill-color-light)',
              color: 'var(--el-text-color-primary)'
            }"
            @selection-change="handleSelectionChange"
          >
            <template #operation="{ row }">
              <template v-if="isStoredMenu(row.id)">
              <el-button
                data-list-action="edit"
                class="reset-margin"
                link
                type="primary"
                :size="size"
                :icon="useRenderIcon(EditPen)"
                @click="openDialog('修改', row)"
              >
                修改
              </el-button>
              <el-button
                data-list-action="create"
                v-show="row.menu_type_code !== 'button'"
                class="reset-margin"
                link
                type="primary"
                :size="size"
                :icon="useRenderIcon(AddFill)"
                @click="openDialog('新增', { parent_id: row.id })"
              >
                新增
              </el-button>
              <el-popconfirm confirm-button-type="danger"
                :title="`是否确认删除菜单「${row.menu_name}」${row?.children?.length > 0 ? '？请先删除下级菜单' : ''}`"
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
              <span v-else>布局分组</span>
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
