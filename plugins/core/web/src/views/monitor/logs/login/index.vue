<script setup lang="ts">
import { ref } from "vue";
import { useRole } from "./hook";
import { getPickerShortcuts } from "../../utils";
import { PureTableBar } from "@/components/RePureTableBar";
import { useRenderIcon } from "@/components/ReIcon/src/hooks";

import Refresh from "~icons/ep/refresh";

defineOptions({
  name: "LoginLog"
});

const formRef = ref();
const tableRef = ref();

const {
  form,
  loading,
  columns,
  dataList,
  pagination,
  selectedNum,
  onSearch,
  resetForm,
  handleSizeChange,
  onSelectionCancel,
  handleCurrentChange,
  handleSelectionChange
} = useRole(tableRef);
</script>

<template>
  <ReListPresentation>
  <div class="main list-page list-presentation-container">
    <ReListHeading title="登录日志" />
    <section class="list-query-panel">
      <el-form
        ref="formRef"
        :inline="true"
        :model="form"
        class="search-form bg-bg_color w-full pl-8 pt-3 overflow-auto list-filters"
      >
        <el-form-item label="用户名" prop="username">
          <el-input
            v-model="form.username"
            placeholder="请输入用户名"
            clearable
            class="w-37.5!"
          />
        </el-form-item>
        <el-form-item label="登录状态" prop="status">
          <el-select
            v-model="form.status"
            placeholder="请选择"
            clearable
            class="w-37.5!"
          >
            <el-option label="成功" value="1" />
            <el-option label="失败" value="0" />
          </el-select>
        </el-form-item>
        <el-form-item label="登录时间" prop="loginTime">
          <el-date-picker
            v-model="form.loginTime"
            :shortcuts="getPickerShortcuts()"
            type="datetimerange"
            value-format="YYYY-MM-DDTHH:mm:ss"
            range-separator="至"
            start-placeholder="开始日期时间"
            end-placeholder="结束日期时间"
          />
        </el-form-item>
        <el-form-item>
          <el-button
            data-list-query="search"
            type="primary"
            :icon="useRenderIcon('ri:search-line')"
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

      <PureTableBar :list-heading="false" title="登录日志" :columns="columns" @refresh="onSearch">
        <template v-slot="{ size, dynamicColumns }">
          <div
            v-if="selectedNum > 0"
            v-motion-fade
            class="bg-(--el-fill-color-light) w-full h-11.5 mb-2 pl-4 flex items-center"
          >
            <div class="flex-auto">
              <span
                style="font-size: var(--el-font-size-base)"
                class="text-[rgba(42,46,54,0.5)] dark:text-[rgba(220,220,242,0.5)]"
              >
                已选 {{ selectedNum }} 项
              </span>
              <el-button data-action="neutral" type="primary" text @click="onSelectionCancel">
                取消选择
              </el-button>
            </div>
          </div>
          <ReListTable
            list-key="index-0"
            engine="pure"
            :list-refresh="onSearch"
            ref="tableRef"
            row-key="id"
            align-whole="center"
            table-layout="auto"
            :loading="loading"
            :size="size"
            adaptive
            :adaptiveConfig="{ offsetBottom: 108 }"
            :data="dataList"
            :columns="dynamicColumns"
            :pagination="{ ...pagination, size }"
            :header-cell-style="{
              background: 'var(--el-fill-color-light)',
              color: 'var(--el-text-color-primary)'
            }"
            @selection-change="handleSelectionChange"
            @page-size-change="handleSizeChange"
            @page-current-change="handleCurrentChange"
          />
        </template>
      </PureTableBar>
    </section>
  </div>

  </ReListPresentation>
</template>

<style lang="scss" scoped>
:deep(.el-dropdown-menu__item i) {
  margin: 0;
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
