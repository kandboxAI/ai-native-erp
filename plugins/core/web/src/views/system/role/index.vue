<script setup lang="ts">
import { useRole } from "./utils/hook";
import { ref, nextTick, onMounted } from "vue";
import { PureTableBar } from "@/components/RePureTableBar";
import { useRenderIcon } from "@/components/ReIcon/src/hooks";
import {
  delay,
  subBefore,
  deviceDetection,
  useResizeObserver
} from "@pureadmin/utils";

// import Database from "~icons/ri/database-2-line";
// import More from "~icons/ep/more-filled";
import Delete from "~icons/ep/delete";
import EditPen from "~icons/ep/edit-pen";
import Refresh from "~icons/ep/refresh";
import Menu from "~icons/ep/menu";
import AddFill from "~icons/ri/add-circle-line";

defineOptions({
  name: "SystemRole"
});

const treeRef = ref();
const formRef = ref();
const tableRef = ref();
const contentRef = ref();
const treeHeight = ref();

const {
  form,
  isShow,
  curRow,
  loading,
  columns,
  rowStyle,
  dataList,
  treeData,
  treeProps,
  menuLoading,
  menuSaving,
  menuReady,
  menuState,
  toggleMenu,
  pagination,
  isExpandAll,
  isSelectAll,
  treeSearchValue,
  bindTab,
  permLoading,
  permSaving,
  permGroups,
  permCheckedSet,
  permScopes,
  permKeyword,
  permModule,
  permModuleOptions,
  roleDataScope,
  advancedScope,
  dataScopeOptions,
  dataScopeLabel,
  miniLoading,
  miniSaving,
  miniCatalog,
  miniCheckedSet,
  miniPortal,
  miniPortalOptions,
  currentMiniGroups,
  portalCheckedCount,
  togglePermission,
  togglePermGroup,
  isPermGroupChecked,
  savePermissions,
  toggleMiniItem,
  toggleMiniGroup,
  toggleMiniPortal,
  portalIds,
  saveMiniappMenus,
  // buttonClass,
  onSearch,
  resetForm,
  openDialog,
  handleMenu,
  handleSave,
  handleDelete,
  filterMethod,
  onQueryChanged,
  // handleDatabase,
  handleSizeChange,
  handleCurrentChange,
  handleSelectionChange
} = useRole(treeRef);

onMounted(() => {
  useResizeObserver(contentRef, async () => {
    await nextTick();
    delay(60).then(() => {
      treeHeight.value = parseFloat(
        subBefore(tableRef.value.getTableDoms().tableWrapper.style.height, "px")
      );
    });
  });
});
</script>

<template>
  <ReListPresentation>
  <div class="main list-page list-presentation-container">
    <ReListHeading title="角色管理" />
    <section class="list-query-panel">
      <el-form
        ref="formRef"
        :inline="true"
        :model="form"
        class="search-form bg-bg_color w-full pl-8 pt-3 overflow-auto list-filters"
      >
        <el-form-item label="角色名称：" prop="role_name">
          <el-input
            v-model="form.role_name"
            placeholder="请输入角色名称"
            clearable
            class="w-45!"
          />
        </el-form-item>
        <el-form-item label="角色编号：" prop="role_no">
          <el-input
            v-model="form.role_no"
            placeholder="请输入角色编号"
            clearable
            class="w-45!"
          />
        </el-form-item>
        <el-form-item label="状态：" prop="is_active">
          <el-select
            v-model="form.is_active"
            placeholder="请选择状态"
            clearable
            class="w-45!"
          >
            <el-option label="已启用" value="true" />
            <el-option label="已停用" value="false" />
          </el-select>
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

      <div
        ref="contentRef"
        :class="['flex', deviceDetection() ? 'flex-wrap' : '']"
      >
        <PureTableBar
          :list-heading="false"
          class="w-full"
          title="角色管理"
          :columns="columns"
          @refresh="onSearch"
        >
          <template #buttons>
            <el-button
              data-list-action="create"
              type="primary"
              :icon="useRenderIcon(AddFill)"
              @click="openDialog()"
            >
              新增角色
            </el-button>
          </template>
          <template v-slot="{ size, dynamicColumns }">
            <ReListTable
              list-key="index-0"
              engine="pure"
              :list-refresh="onSearch"
              ref="tableRef"
              align-whole="center"
              showOverflowTooltip
              table-layout="auto"
              :loading="loading"
              :size="size"
              adaptive
              :row-style="rowStyle"
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
            >
              <template #operation="{ row }">
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
                <el-popconfirm confirm-button-type="danger"
                  v-if="!row.is_builtin"
                  :title="`是否确认删除角色「${row.role_name}」`"
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
                <el-button
                  data-action="edit"
                  class="reset-margin"
                  link
                  type="primary"
                  :size="size"
                  :icon="useRenderIcon(Menu)"
                  @click="handleMenu(row)"
                >
                  权限
                </el-button>
                <!-- <el-dropdown>
                <el-button
                  class="ml-3 mt-[2px]"
                  link
                  type="primary"
                  :size="size"
                  :icon="useRenderIcon(More)"
                />
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item>
                      <el-button
                        :class="buttonClass"
                        link
                        type="primary"
                        :size="size"
                        :icon="useRenderIcon(Menu)"
                        @click="handleMenu"
                      >
                        菜单权限
                      </el-button>
                    </el-dropdown-item>
                    <el-dropdown-item>
                      <el-button
                        :class="buttonClass"
                        link
                        type="primary"
                        :size="size"
                        :icon="useRenderIcon(Database)"
                        @click="handleDatabase"
                      >
                        数据权限
                      </el-button>
                    </el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown> -->
              </template>
            </ReListTable>
          </template>
        </PureTableBar>
      </div>
    </section>

    <el-drawer
      v-model="isShow"
      :title="`角色权限${curRow?.role_name ? `（${curRow.role_name}）` : ''}`"
      size="760px"
      destroy-on-close
    >
      <el-tabs v-model="bindTab">
        <el-tab-pane label="菜单" name="menu">
          <el-input
            v-model="treeSearchValue"
            placeholder="请输入菜单进行搜索"
            class="mb-1"
            clearable
            @input="onQueryChanged"
          />
          <div class="flex flex-wrap">
            <el-checkbox v-model="isExpandAll" label="展开/折叠" />
            <el-checkbox
              v-model="isSelectAll"
              label="全选/全不选"
              :disabled="!menuReady || menuSaving"
            />
          </div>
          <p class="mb-2 text-xs text-(--el-text-color-secondary)">
            可见菜单按左侧菜单分组。隐藏路由、按钮及停用项可在「其他菜单权限」中单独配置。菜单与接口权限分别保存。
          </p>
          <el-tree-v2
            ref="treeRef"
            v-loading="menuLoading"
            :data="treeData"
            :props="treeProps"
            :height="treeHeight || 520"
            :filter-method="filterMethod"
          >
            <template #default="{ node, data }">
              <el-checkbox
                :model-value="menuState(data).checked"
                :indeterminate="menuState(data).indeterminate"
                :disabled="!menuReady || menuSaving"
                @click.stop
                @change="value => toggleMenu(data, value === true)"
              >
                {{ node.label }}
              </el-checkbox>
            </template>
          </el-tree-v2>
          <div class="bind-footer">
            <el-button
              data-action="primary"
              type="primary"
              :disabled="!menuReady"
              :loading="menuSaving"
              @click="handleSave"
              >保存菜单</el-button
            >
          </div>
        </el-tab-pane>

        <el-tab-pane label="接口" name="api">
          <div v-loading="permLoading" class="bind-pane">
            <div class="bind-toolbar">
              <el-input
                v-model="permKeyword"
                clearable
                placeholder="搜索名称 / 权限标识 / 模块"
              />
              <el-select
                v-model="permModule"
                clearable
                filterable
                placeholder="模块"
              >
                <el-option
                  v-for="item in permModuleOptions"
                  :key="item.value"
                  :label="item.label"
                  :value="item.value"
                />
              </el-select>
              <el-button
                data-action="neutral"
                link
                type="primary"
                @click="advancedScope = !advancedScope"
              >
                {{ advancedScope ? "收起数据范围" : "数据范围" }}
              </el-button>
            </div>
            <p class="bind-hint">
              新勾选的接口使用角色默认范围「{{
                dataScopeLabel(roleDataScope)
              }}」。
            </p>
            <el-empty
              v-if="!permLoading && !permGroups.length"
              description="无匹配的接口权限"
            />
            <div v-else class="bind-scroll">
              <div
                v-for="group in permGroups"
                :key="group.module"
                class="bind-group"
              >
                <div class="bind-group-head">
                  <span>{{ group.moduleLabel }}</span>
                  <span class="bind-code">{{ group.module }}</span>
                  <el-button
                    data-action="neutral"
                    link
                    type="primary"
                    @click="
                      togglePermGroup(
                        group.items,
                        !isPermGroupChecked(group.items)
                      )
                    "
                  >
                    {{
                      isPermGroupChecked(group.items) ? "取消本组" : "全选本组"
                    }}
                  </el-button>
                </div>
                <div
                  v-for="item in group.items"
                  :key="item.id"
                  class="bind-row"
                >
                  <el-checkbox
                    :model-value="permCheckedSet.has(item.id)"
                    @change="value => togglePermission(item.id, Boolean(value))"
                  >
                    {{ item.permission_name }}（{{ item.permission_key }}）
                  </el-checkbox>
                  <el-select
                    v-if="advancedScope && permCheckedSet.has(item.id)"
                    v-model="permScopes[item.id]"
                    size="small"
                    class="scope-select"
                  >
                    <el-option
                      v-for="option in dataScopeOptions"
                      :key="option.value"
                      :label="option.label"
                      :value="option.value"
                    />
                  </el-select>
                </div>
              </div>
            </div>
            <div class="bind-footer">
              <el-button
                data-action="primary"
                type="primary"
                :loading="permSaving"
                @click="savePermissions"
              >
                保存接口权限
              </el-button>
            </div>
          </div>
        </el-tab-pane>

        <el-tab-pane label="小程序菜单" name="miniapp">
          <div v-loading="miniLoading" class="bind-pane">
            <p class="bind-hint">
              勾选该角色在小程序各门户中可见的菜单；保存时一次提交全部门户。
            </p>
            <el-radio-group v-model="miniPortal" size="small" class="mb-2">
              <el-radio-button
                v-for="portal in miniPortalOptions"
                :key="portal.value"
                :value="portal.value"
              >
                {{ portal.label }}（{{ portalCheckedCount(portal.value) }}/{{
                  portalIds(portal.value).length
                }}）
              </el-radio-button>
            </el-radio-group>
            <div class="portal-block">
              <div class="bind-group-head">
                <span>本门户</span>
                <el-button
                  data-action="neutral"
                  link
                  type="primary"
                  @click="toggleMiniPortal(miniPortal, true)"
                >
                  全选
                </el-button>
                <el-button
                  data-action="warning"
                  link
                  type="warning"
                  @click="toggleMiniPortal(miniPortal, false)"
                >
                  清空
                </el-button>
              </div>
              <el-empty
                v-if="!currentMiniGroups.length"
                description="该门户暂无小程序菜单"
              />
              <div v-else class="bind-scroll">
                <div
                  v-for="group in currentMiniGroups"
                  :key="group.group_key ?? ''"
                  class="bind-group"
                >
                  <div class="bind-group-head">
                    <span>{{ group.group_name || "未分组" }}</span>
                    <el-button
                      data-action="neutral"
                      link
                      type="primary"
                      @click="
                        toggleMiniGroup(
                          group.items.map(item => item.id),
                          !group.items.every(item =>
                            miniCheckedSet.has(item.id)
                          )
                        )
                      "
                    >
                      {{
                        group.items.every(item => miniCheckedSet.has(item.id))
                          ? "取消本组"
                          : "全选本组"
                      }}
                    </el-button>
                  </div>
                  <el-checkbox
                    v-for="item in group.items"
                    :key="item.id"
                    :model-value="miniCheckedSet.has(item.id)"
                    @change="value => toggleMiniItem(item.id, Boolean(value))"
                  >
                    {{ item.menu_name }}
                  </el-checkbox>
                </div>
              </div>
            </div>
            <div class="bind-footer">
              <el-button
                data-action="primary"
                type="primary"
                :loading="miniSaving"
                @click="saveMiniappMenus"
              >
                保存小程序菜单
              </el-button>
            </div>
          </div>
        </el-tab-pane>
      </el-tabs>
    </el-drawer>
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

.bind-pane {
  min-height: 240px;
}

.bind-toolbar {
  display: grid;
  grid-template-columns: 1fr 180px auto;
  gap: 10px;
  align-items: center;
}

.bind-hint {
  margin: 10px 0;
  font-size: 13px;
  color: #8a95a5;
}

.bind-scroll {
  max-height: calc(100vh - 280px);
  overflow: auto;
}

.bind-group {
  padding-bottom: 8px;
  margin-bottom: 14px;
  border-bottom: 1px solid #f0f3f7;
}

.bind-group-head {
  display: flex;
  gap: 10px;
  align-items: center;
  margin-bottom: 8px;
  font-weight: 650;
}

.bind-code {
  font-size: 12px;
  font-weight: 400;
  color: #8a95a5;
}

.bind-row {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
  padding: 4px 0;
}

.scope-select {
  width: 140px;
}

.portal-block + .portal-block {
  margin-top: 18px;
}

.bind-footer {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}
</style>
