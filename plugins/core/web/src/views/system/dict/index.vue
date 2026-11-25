<template>
  <ReListPresentation>
  <div class="sys-page list-page list-presentation-container">
    <section class="list-section">
      <ReMenuViews v-model="activeTab" class="dict-tabs list-tabs" @tab-change="onTabChange">
        <el-tab-pane label="字典类型" name="types">
          <div class="tab-toolbar">
            <span />
          </div>
          <ReListHeading data-list-key="index-0">
            <template #title>字典类型</template>
          </ReListHeading>
          <section class="list-query-panel">
            <div class="filter-panel list-filters">
              <el-form
                :model="typeQueryForm"
                label-position="top"
                class="query-form"
              >
                <div class="filter-row dict-filter-row">
                  <el-form-item label="关键词">
                    <el-input
                      v-model="typeQueryForm.keyword"
                      clearable
                      placeholder="请输入编码 / 名称 / 说明"
                    />
                  </el-form-item>
                  <el-form-item label="状态">
                    <el-select
                      v-model="typeQueryForm.is_active"
                      placeholder="请选择状态"
                      clearable
                      style="width: 100%"
                    >
                      <el-option label="启用" :value="true" />
                      <el-option label="停用" :value="false" />
                    </el-select>
                  </el-form-item>
                  <div class="query-actions">
                    <el-button
                      data-list-query="search"
                      class="search-btn"
                      @click="searchTypes"
                      >搜索</el-button
                    >
                    <el-button
                      data-list-query="reset"
                      class="reset-btn"
                      @click="resetTypeQuery"
                      >重置</el-button
                    >
                  </div>
                </div>
              </el-form>
            </div>
            <div class="table-panel list-section">
              <ReListTable
                :list-heading="false"
                list-key="index-0"
                :list-refresh="loadTypes"
                v-loading="typeLoading"
                :data="typeTableData"
                row-key="id"
                class="data-table"
              >
                <el-table-column
                  prop="dict_code"
                  label="字典编码"
                  min-width="120"
                  show-overflow-tooltip
                />
                <el-table-column
                  prop="dict_name"
                  label="字典名称"
                  min-width="120"
                  show-overflow-tooltip
                />
                <el-table-column
                  prop="description"
                  label="说明"
                  min-width="160"
                  show-overflow-tooltip
                >
                  <template #default="{ row }">{{
                    row.description || "—"
                  }}</template>
                </el-table-column>
                <el-table-column
                  prop="is_active"
                  label="状态"
                  width="88"
                  align="center"
                >
                  <template #default="{ row }">
                    <el-tag
                      :type="row.is_active ? 'success' : 'info'"
                      size="small"
                    >
                      {{ row.is_active ? "启用" : "停用" }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column
                  prop="is_builtin"
                  label="来源"
                  width="88"
                  align="center"
                >
                  <template #default="{ row }">
                    <el-tag
                      :type="row.is_builtin ? 'warning' : 'info'"
                      size="small"
                    >
                      {{ row.is_builtin ? "内置" : "自建" }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column
                  prop="is_tenant_extensible"
                  label="可扩展"
                  width="80"
                  align="center"
                >
                  <template #default="{ row }">
                    {{ row.is_tenant_extensible ? "是" : "否" }}
                  </template>
                </el-table-column>
                <el-table-column
                  prop="updated_at"
                  label="更新时间"
                  min-width="150"
                >
                  <template #default="{ row }">{{
                    formatDt(row.updated_at)
                  }}</template>
                </el-table-column>
                <el-table-column label="操作" width="220" fixed="right">
                  <template #default="{ row }">
                    <span
                      class="action-text primary"
                      @click="openItemsForType(row as DictionaryTypeRow)"
                      >字典项</span
                    >
                    <span
                      class="action-text success"
                      @click="openEditType(row as DictionaryTypeRow)"
                      >编辑</span
                    >
                    <span
                      v-if="!row.is_builtin"
                      class="action-text danger"
                      @click="removeType(row as DictionaryTypeRow)"
                      >删除</span
                    >
                  </template>
                </el-table-column>

                <template #list-actions
                  ><div class="tab-actions">
                    <el-button
                      data-list-action="create"
                      data-action="primary"
                      type="primary"
                      :icon="Plus"
                      @click="openCreateType"
                      >新建字典类型</el-button
                    >
                    <el-button
                      data-list-action="export"
                      data-action="export"
                      :icon="Download"
                      @click="exportTypesCsv"
                      >导出字典类型</el-button
                    >
                  </div></template
                >

                <template #list-pagination
                  ><div class="table-footer">

                    <ReListPagination
                      v-model:current-page="typeQuery.page"
                      v-model:page-size="typeQuery.page_size"
                      :total="typeTotal"
                      @current-change="loadTypes" @size-change="onTypePageSizeChange" /></div
                ></template>
              </ReListTable>
            </div>
          </section>
        </el-tab-pane>

        <el-tab-pane label="字典项" name="items">
          <div class="tab-toolbar">
            <span />
          </div>
          <ReListHeading data-list-key="index-1">
            <template #title>字典项</template>
          </ReListHeading>
          <section class="list-query-panel">
            <div class="filter-panel list-filters">
              <el-form label-position="top" class="query-form">
                <div class="filter-row dict-filter-row">
                  <el-form-item label="关键词">
                    <el-input
                      v-model="itemQueryForm.keyword"
                      clearable
                      placeholder="请输入字典编码 / 名称 / 取值编码 / 取值名称"
                      @keyup.enter="searchItems"
                    />
                  </el-form-item>
                  <el-form-item label="字典类型">
                    <el-select
                      v-model="itemTypeFilterCode"
                      placeholder="请选择字典类型"
                      clearable
                      filterable
                      style="width: 100%"
                      @change="onItemTypeFilterChange"
                      @clear="onItemTypeFilterChange"
                    >
                      <el-option
                        v-for="d in dictOptions"
                        :key="d.id"
                        :label="`${d.dict_code} — ${d.dict_name}`"
                        :value="d.dict_code"
                      />
                    </el-select>
                  </el-form-item>
                  <el-form-item label="状态">
                    <el-select
                      v-model="itemQueryForm.is_active"
                      placeholder="请选择状态"
                      clearable
                      style="width: 100%"
                    >
                      <el-option label="启用" value="active" />
                      <el-option label="停用" value="inactive" />
                    </el-select>
                  </el-form-item>
                  <div class="query-actions">
                    <el-button
                      data-list-query="search"
                      class="search-btn"
                      @click="searchItems"
                      >搜索</el-button
                    >
                    <el-button
                      data-list-query="reset"
                      class="reset-btn"
                      @click="resetItemQuery"
                      >重置</el-button
                    >
                  </div>
                </div>
              </el-form>
            </div>
            <div class="table-panel list-section">
              <ReListTable
                :list-heading="false"
                list-key="index-1"
                :list-refresh="searchItems"
                v-loading="itemLoading"
                :data="itemTableData"
                row-key="id"
                class="data-table"
              >
                <el-table-column
                  prop="dict_code"
                  label="字典编码"
                  min-width="110"
                  show-overflow-tooltip
                />
                <el-table-column
                  prop="dict_name"
                  label="字典名称"
                  min-width="110"
                  show-overflow-tooltip
                />
                <el-table-column
                  prop="dict_code"
                  label="说明"
                  min-width="120"
                  show-overflow-tooltip
                >
                  <template #default="{ row }">{{
                    typeDescription(row.dict_code)
                  }}</template>
                </el-table-column>
                <el-table-column
                  prop="item_code"
                  label="取值编码（存储值）"
                  min-width="120"
                  show-overflow-tooltip
                />
                <el-table-column
                  prop="item_name"
                  label="取值名称（展示）"
                  min-width="120"
                  show-overflow-tooltip
                />
                <el-table-column
                  prop="is_builtin"
                  label="内置"
                  width="72"
                  align="center"
                >
                  <template #default="{ row }">{{
                    row.is_builtin ? "是" : "否"
                  }}</template>
                </el-table-column>
                <el-table-column
                  prop="sort_no"
                  label="排序"
                  width="72"
                  align="center"
                />
                <el-table-column
                  prop="is_active"
                  label="状态"
                  width="88"
                  align="center"
                >
                  <template #default="{ row }">
                    <el-tag
                      :type="row.is_active ? 'success' : 'info'"
                      size="small"
                    >
                      {{ row.is_active ? "启用" : "停用" }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column
                  prop="remark"
                  label="备注"
                  min-width="120"
                  show-overflow-tooltip
                >
                  <template #default="{ row }">{{ row.remark || "—" }}</template>
                </el-table-column>
                <el-table-column
                  prop="updated_at"
                  label="更新时间"
                  min-width="150"
                >
                  <template #default="{ row }">{{
                    formatDt(row.updated_at)
                  }}</template>
                </el-table-column>
                <el-table-column label="操作" width="140" fixed="right">
                  <template #default="{ row }">
                    <span
                      class="action-text success"
                      @click="openEditItem(row as SystemDictionaryRow)"
                      >编辑</span
                    >
                    <span
                      v-if="row.is_builtin"
                      class="action-text"
                      @click="toggleItemActive(row as SystemDictionaryRow)"
                      >{{ row.is_active ? "停用" : "启用" }}</span
                    >
                    <span
                      v-else
                      class="action-text danger"
                      @click="removeItem(row as SystemDictionaryRow)"
                      >删除</span
                    >
                  </template>
                </el-table-column>

                <template #list-actions
                  ><div class="tab-actions">
                    <el-button
                      data-list-action="create"
                      data-action="primary"
                      type="primary"
                      :icon="Plus"
                      @click="openCreateItem"
                    >
                      新增字典项
                    </el-button>
                    <el-button
                      data-list-action="export"
                      data-action="export"
                      :icon="Download"
                      @click="exportItemsCsv"
                    >
                      导出字典项
                    </el-button>
                  </div></template
                >

                <template #list-pagination
                  ><div class="table-footer">

                    <ReListPagination
                      v-model:current-page="itemQuery.page"
                      v-model:page-size="itemQuery.page_size"
                      :total="itemTotal"
                      @current-change="applyItemFilter" @size-change="onItemPageSizeChange" /></div
                ></template>
              </ReListTable>
            </div>
          </section>
        </el-tab-pane>
      </ReMenuViews>
    </section>

    <!-- 字典类型 -->
    <el-dialog
      v-model="typeDialogVisible"
      :title="editingTypeId ? '编辑字典类型' : '新建字典类型'"
      width="520px"
      destroy-on-close
      @closed="resetTypeForm"
    >
      <el-form
        ref="typeFormRef"
        :model="typeForm"
        :rules="typeRules"
        label-position="top"
      >
        <el-form-item label="字典编码" prop="dict_code">
          <el-input
            v-model="typeForm.dict_code"
            maxlength="64"
            placeholder="小写英文，如 edu_leave_type；创建后不可修改"
            :disabled="!!editingTypeId"
          />
        </el-form-item>
        <el-form-item label="字典名称" prop="dict_name">
          <el-input
            v-model="typeForm.dict_name"
            maxlength="128"
            placeholder="中文名称"
          />
        </el-form-item>
        <el-form-item label="说明" prop="description">
          <el-input
            v-model="typeForm.description"
            type="textarea"
            :rows="2"
            maxlength="512"
            show-word-limit
            placeholder="可选"
          />
        </el-form-item>
        <el-form-item label="租户可扩展" prop="is_tenant_extensible">
          <el-switch
            v-model="typeForm.is_tenant_extensible"
            :disabled="editingTypeBuiltin"
            active-text="允许新增字典项"
            inactive-text="不允许"
          />
        </el-form-item>
        <el-form-item label="状态" prop="is_active">
          <el-switch
            v-model="typeForm.is_active"
            active-text="启用"
            inactive-text="停用"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button data-action="primary" type="primary" @click="submitType">确定</el-button>
        <el-button data-action="neutral" class="btn-cancel" @click="typeDialogVisible = false"
          >取消</el-button
        >
      </template>
    </el-dialog>

    <!-- 字典项 -->
    <el-dialog
      v-model="itemDialogVisible"
      :title="editingItemId ? '编辑字典项' : '新增字典项'"
      width="520px"
      destroy-on-close
      @closed="resetItemForm"
    >
      <el-form
        ref="itemFormRef"
        :model="itemForm"
        :rules="itemRules"
        label-position="top"
      >
        <el-form-item v-if="!editingItemId" label="所属字典" prop="dict_id">
          <el-select
            v-model="itemForm.dict_id"
            filterable
            placeholder="请选择"
            style="width: 100%"
          >
            <el-option
              v-for="d in extensibleDictOptions"
              :key="d.id"
              :label="`${d.dict_code} — ${d.dict_name}`"
              :value="d.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item v-else label="所属字典">
          <el-input :model-value="currentDictionaryLabel" disabled />
        </el-form-item>
        <el-form-item label="取值编码（存储值）" prop="item_code">
          <el-input
            v-model="itemForm.item_code"
            maxlength="64"
            :disabled="editingItemBuiltin"
            placeholder="小写英文，业务表中保存的值"
          />
        </el-form-item>
        <el-form-item label="取值名称（展示）" prop="item_name">
          <el-input
            v-model="itemForm.item_name"
            maxlength="128"
            placeholder="界面展示文案"
          />
        </el-form-item>
        <el-form-item label="排序" prop="sort_no">
          <el-input-number
            v-model="itemForm.sort_no"
            :min="0"
            :max="9999"
            controls-position="right"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="状态" prop="is_active">
          <el-switch
            v-model="itemForm.is_active"
            active-text="启用"
            inactive-text="停用"
          />
        </el-form-item>
        <el-form-item label="备注" prop="remark">
          <el-input
            v-model="itemForm.remark"
            type="textarea"
            :rows="2"
            maxlength="512"
            show-word-limit
            placeholder="可选"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button data-action="primary" type="primary" @click="submitItem">确定</el-button>
        <el-button data-action="neutral" class="btn-cancel" @click="itemDialogVisible = false"
          >取消</el-button
        >
      </template>
    </el-dialog>
  </div>

  </ReListPresentation>
</template>

<script setup lang="ts">
import { useMenuNavigation, useMenuView } from "@/utils/menuView";
import { useRoute } from "vue-router";
import { hasPerms } from "@/utils/auth";
import { Download, Plus } from "@element-plus/icons-vue";
import dayjs from "dayjs";
import type { FormInstance, FormRules } from "element-plus";
import { ElMessage, ElMessageBox } from "element-plus";
import { computed, onMounted, reactive, ref } from "vue";
import type {
  DictionaryTypeRow,
  SystemDictionaryRow
} from "@/api/systemDictionary";
import {
  createDictionary,
  createDictionaryItem,
  deleteDictionary,
  deleteDictionaryItem,
  listDictionaries,
  listDictionaryEntries,
  updateDictionary,
  updateDictionaryItem
} from "@/api/systemDictionary";
import { getHttpErrorMessage } from "@/utils/http";
import { useBasicDataStoreHook } from "@/store/modules/basicData";

defineOptions({ name: "DictionaryManagement" });

const SS_TAB = "dictionary-management:activeTab";

const activeTab = useMenuView("types", ["types","items"]);
const menuContext = { ...useRoute().query };
const configuredMenu = useRoute().meta.menuView != null;
const navigateMenu = useMenuNavigation();

const typeQueryForm = reactive<{
  keyword: string;
  is_active: boolean | undefined;
}>({
  keyword: "",
  is_active: undefined
});
const typeQuery = reactive({ page: 1, page_size: 20 });
const typeLoading = ref(false);
const typeTableData = ref<DictionaryTypeRow[]>([]);
const typeTotal = ref(0);

const dictOptions = ref<DictionaryTypeRow[]>([]);
const basicDataStore = useBasicDataStoreHook();

const itemQueryForm = reactive<{
  keyword: string;
  is_active: boolean | undefined;
}>({
  keyword: "",
  is_active: undefined
});
const itemQuery = reactive({ page: 1, page_size: 20 });
const itemLoading = ref(false);
const itemAllData = ref<SystemDictionaryRow[]>([]);
const itemTableData = ref<SystemDictionaryRow[]>([]);
const itemTotal = ref(0);
const itemTypeFilterCode = ref(String(menuContext.dict_code || ""));

const typeDialogVisible = ref(false);
const editingTypeId = ref<string | null>(null);
const typeFormRef = ref<FormInstance>();
const typeForm = reactive({
  dict_code: "",
  dict_name: "",
  description: "",
  is_tenant_extensible: true,
  is_active: true
});
const editingTypeBuiltin = ref(false);

const typeRules: FormRules = {
  dict_code: [{ required: true, message: "请输入字典编码", trigger: "blur" }],
  dict_name: [{ required: true, message: "请输入字典名称", trigger: "blur" }]
};

const itemDialogVisible = ref(false);
const editingItemId = ref<string | null>(null);
const itemFormRef = ref<FormInstance>();
const itemForm = reactive({
  dict_id: "",
  item_code: "",
  item_name: "",
  sort_no: 0 as number | null,
  is_active: true,
  remark: ""
});
const editingItemBuiltin = ref(false);

const itemRules: FormRules = {
  dict_id: [{ required: true, message: "请选择字典", trigger: "change" }],
  item_code: [{ required: true, message: "请输入取值编码", trigger: "blur" }],
  item_name: [{ required: true, message: "请输入取值名称", trigger: "blur" }]
};

const currentDictionaryLabel = computed(() => {
  const d = dictOptions.value.find(x => x.id === itemForm.dict_id);
  return d ? `${d.dict_code} — ${d.dict_name}` : "—";
});

/** 只有租户可扩展的字典允许新增字典项 */
const extensibleDictOptions = computed(() =>
  dictOptions.value.filter(d => d.is_tenant_extensible)
);

const selectedItemType = computed(() => {
  if (!itemTypeFilterCode.value) return null;
  return (
    dictOptions.value.find(x => x.dict_code === itemTypeFilterCode.value) ??
    null
  );
});

const selectedItemDictionaryId = computed(() =>
  selectedItemType.value?.is_tenant_extensible ? selectedItemType.value.id : ""
);

const typeDescriptionMap = computed(() => {
  const map: Record<string, string> = {};
  for (const d of dictOptions.value) {
    map[d.dict_code] = d.description?.trim() || "";
  }
  return map;
});

function typeDescription(code: string) {
  const text = typeDescriptionMap.value[code];
  return text || "—";
}

function formatDt(v: string) {
  return v ? dayjs(v).format("YYYY-M-D HH:mm") : "—";
}

function persistUiState() {
  try {
    sessionStorage.setItem(SS_TAB, activeTab.value);
  } catch {
    /* ignore */
  }
}

function restoreUiState() {
  try {
    const t = sessionStorage.getItem(SS_TAB);
    if (!configuredMenu && (t === "types" || t === "items")) activeTab.value = t;
  } catch {
    /* ignore */
  }
}

async function loadDictOptions() {
  if (!hasPerms("dictionary:list")) return;
  try {
    const all: DictionaryTypeRow[] = [];
    let page = 1;
    const page_size = 100;
    while (true) {
      const res = await listDictionaries({ page, page_size });
      const items = res.data.items ?? [];
      all.push(...items);
      const total = res.data.total ?? 0;
      if (all.length >= total || items.length < page_size) break;
      page += 1;
    }
    dictOptions.value = all;
  } catch (e) {
    ElMessage.error(getHttpErrorMessage(e, "加载字典类型失败"));
  }
}

async function loadTypes() {
  typeLoading.value = true;
  try {
    const res = await listDictionaries({
      page: typeQuery.page,
      page_size: typeQuery.page_size,
      keyword: typeQueryForm.keyword.trim() || undefined,
      is_active: typeQueryForm.is_active
    });
    typeTableData.value = res.data.items ?? [];
    typeTotal.value = res.data.total ?? 0;
  } catch (e) {
    ElMessage.error(getHttpErrorMessage(e, "加载失败"));
  } finally {
    typeLoading.value = false;
  }
}

async function searchTypes() {
  typeQuery.page = 1;
  await loadTypes();
}

async function resetTypeQuery() {
  typeQueryForm.keyword = "";
  typeQueryForm.is_active = undefined;
  typeQuery.page = 1;
  await loadTypes();
}

async function onTypePageSizeChange() {
  typeQuery.page = 1;
  await loadTypes();
}

async function loadAllEntries() {
  itemLoading.value = true;
  try {
    const all: SystemDictionaryRow[] = [];
    let page = 1;
    const page_size = 100;
    while (true) {
      const res = await listDictionaryEntries({ page, page_size });
      const items = res.data.items ?? [];
      all.push(...items);
      const total = res.data.total ?? 0;
      if (all.length >= total || items.length < page_size) break;
      page += 1;
    }
    itemAllData.value = all;
    applyItemFilter();
  } catch (e) {
    ElMessage.error(getHttpErrorMessage(e, "加载字典项失败"));
  } finally {
    itemLoading.value = false;
  }
}

function applyItemFilter() {
  const kw = itemQueryForm.keyword.trim().toLowerCase();
  let rows = itemAllData.value;

  if (itemQueryForm.is_active !== undefined) {
    rows = rows.filter(r => r.is_active === itemQueryForm.is_active);
  }

  if (itemTypeFilterCode.value) {
    rows = rows.filter(r => r.dict_code === itemTypeFilterCode.value);
  }

  if (kw) {
    rows = rows.filter(r => {
      const desc = typeDescriptionMap.value[r.dict_code] ?? "";
      return [
        r.dict_code,
        r.dict_name,
        desc,
        r.item_code,
        r.item_name,
        r.remark ?? ""
      ].some(s => s.toLowerCase().includes(kw));
    });
  }

  itemTotal.value = rows.length;
  const start = (itemQuery.page - 1) * itemQuery.page_size;
  itemTableData.value = rows.slice(start, start + itemQuery.page_size);
}

function searchItems() {
  itemQuery.page = 1;
  applyItemFilter();
}

function resetItemQuery() {
  itemQueryForm.keyword = "";
  itemQueryForm.is_active = undefined;
  itemQuery.page = 1;
  applyItemFilter();
}

function onItemTypeFilterChange() {
  itemQuery.page = 1;
  applyItemFilter();
}

function onItemPageSizeChange() {
  itemQuery.page = 1;
  applyItemFilter();
}

function onTabChange(name: string | number) {
  if (name === "types") activeTab.value = "types";
  else if (name === "items") activeTab.value = "items";
  persistUiState();
  if (activeTab.value === "items") void loadAllEntries();
}

async function openItemsForType(row: DictionaryTypeRow) {
  if (navigateMenu("items", { dict_code: row.dict_code })) return;
  itemTypeFilterCode.value = row.dict_code;
  itemQueryForm.keyword = "";
  itemQueryForm.is_active = undefined;
  itemQuery.page = 1;
  activeTab.value = "items";
  persistUiState();
  await loadAllEntries();
}

function openCreateType() {
  editingTypeId.value = null;
  editingTypeBuiltin.value = false;
  Object.assign(typeForm, {
    dict_code: "",
    dict_name: "",
    description: "",
    is_tenant_extensible: true,
    is_active: true
  });
  typeDialogVisible.value = true;
}

function openEditType(row: DictionaryTypeRow) {
  editingTypeId.value = row.id;
  editingTypeBuiltin.value = row.is_builtin;
  Object.assign(typeForm, {
    dict_code: row.dict_code,
    dict_name: row.dict_name,
    description: row.description ?? "",
    is_tenant_extensible: row.is_tenant_extensible,
    is_active: row.is_active
  });
  typeDialogVisible.value = true;
}

function resetTypeForm() {
  editingTypeId.value = null;
  typeFormRef.value?.clearValidate();
}

async function submitType() {
  try {
    await typeFormRef.value?.validate();
  } catch {
    return;
  }
  const payload = {
    dict_code: typeForm.dict_code.trim(),
    dict_name: typeForm.dict_name.trim(),
    description: typeForm.description.trim() || null,
    is_tenant_extensible: typeForm.is_tenant_extensible,
    is_active: typeForm.is_active
  };
  try {
    if (editingTypeId.value) {
      const { dict_code: _code, ...rest } = payload;
      await updateDictionary(editingTypeId.value, rest);
      ElMessage.success("已保存");
    } else {
      await createDictionary(payload);
      ElMessage.success("已新增");
    }
    basicDataStore.invalidateDictOptions();
    typeDialogVisible.value = false;
    await loadTypes();
    await loadDictOptions();
    if (activeTab.value === "items") await loadAllEntries();
  } catch (e) {
    ElMessage.error(getHttpErrorMessage(e, "保存失败"));
  }
}

async function removeType(row: DictionaryTypeRow) {
  await ElMessageBox.confirm(
    `确定删除字典「${row.dict_name}」？其下的字典项将一并删除。`,
    "删除",
    {
      confirmButtonClass: "app-button-danger",
      type: "warning"
    }
  );
  try {
    await deleteDictionary(row.id);
    basicDataStore.invalidateDictOptions();
    ElMessage.success("已删除");
    await loadTypes();
    await loadDictOptions();
    if (activeTab.value === "items") await loadAllEntries();
  } catch (e) {
    if (e !== "cancel") ElMessage.error(getHttpErrorMessage(e, "删除失败"));
  }
}

function openCreateItem() {
  editingItemId.value = null;
  editingItemBuiltin.value = false;
  Object.assign(itemForm, {
    dict_id: selectedItemDictionaryId.value,
    item_code: "",
    item_name: "",
    sort_no: 0,
    is_active: true,
    remark: ""
  });
  if (!dictOptions.value.length) void loadDictOptions();
  itemDialogVisible.value = true;
}

function openEditItem(row: SystemDictionaryRow) {
  editingItemId.value = row.id;
  editingItemBuiltin.value = row.is_builtin;
  Object.assign(itemForm, {
    dict_id: row.dict_id,
    item_code: row.item_code,
    item_name: row.item_name,
    sort_no: row.sort_no,
    is_active: row.is_active,
    remark: row.remark ?? ""
  });
  itemDialogVisible.value = true;
}

function resetItemForm() {
  editingItemId.value = null;
  itemFormRef.value?.clearValidate();
}

async function submitItem() {
  try {
    await itemFormRef.value?.validate();
  } catch {
    return;
  }
  const base = {
    dict_id: itemForm.dict_id.trim(),
    item_code: itemForm.item_code.trim(),
    item_name: itemForm.item_name.trim(),
    sort_no: itemForm.sort_no,
    is_active: itemForm.is_active,
    remark: itemForm.remark.trim() || null
  };
  try {
    if (editingItemId.value) {
      await updateDictionaryItem(editingItemId.value, {
        ...(editingItemBuiltin.value ? {} : { item_code: base.item_code }),
        item_name: base.item_name,
        sort_no: base.sort_no,
        is_active: base.is_active,
        remark: base.remark
      });
      ElMessage.success("已保存");
    } else {
      await createDictionaryItem(base);
      ElMessage.success("已新增");
    }
    basicDataStore.invalidateDictOptions();
    itemDialogVisible.value = false;
    await loadAllEntries();
  } catch (e) {
    ElMessage.error(getHttpErrorMessage(e, "保存失败"));
  }
}

async function removeItem(row: SystemDictionaryRow) {
  await ElMessageBox.confirm(`确定删除字典项「${row.item_name}」？`, "删除", {
    confirmButtonClass: "app-button-danger",
    type: "warning"
  });
  try {
    await deleteDictionaryItem(row.id);
    basicDataStore.invalidateDictOptions();
    ElMessage.success("已删除");
    await loadAllEntries();
  } catch (e) {
    if (e !== "cancel") ElMessage.error(getHttpErrorMessage(e, "删除失败"));
  }
}

async function toggleItemActive(row: SystemDictionaryRow) {
  const next = !row.is_active;
  try {
    await updateDictionaryItem(row.id, { is_active: next });
    basicDataStore.invalidateDictOptions();
    ElMessage.success(next ? "已启用" : "已停用");
    await loadAllEntries();
  } catch (e) {
    ElMessage.error(getHttpErrorMessage(e, "操作失败"));
  }
}

function exportTypesCsv() {
  const rows = typeTableData.value;
  if (!rows.length) {
    ElMessage.warning("暂无可导出数据");
    return;
  }
  const h = [
    "字典编码",
    "字典名称",
    "说明",
    "内置",
    "租户可扩展",
    "状态",
    "创建时间",
    "更新时间"
  ];
  const lines = rows.map(r =>
    [
      r.dict_code,
      r.dict_name,
      r.description ?? "",
      r.is_builtin ? "是" : "否",
      r.is_tenant_extensible ? "是" : "否",
      r.is_active ? "启用" : "停用",
      formatDt(r.created_at),
      formatDt(r.updated_at)
    ]
      .map(c => `"${String(c).replace(/"/g, '""')}"`)
      .join(",")
  );
  downloadCsv(
    `字典类型_${dayjs().format("YYYY-MM-DD_HHmm")}.csv`,
    [h.join(","), ...lines].join("\r\n")
  );
}

function exportItemsCsv() {
  const kw = itemQueryForm.keyword.trim().toLowerCase();
  let rows = itemAllData.value;
  if (itemQueryForm.is_active !== undefined) {
    rows = rows.filter(r => r.is_active === itemQueryForm.is_active);
  }
  if (itemTypeFilterCode.value) {
    rows = rows.filter(r => r.dict_code === itemTypeFilterCode.value);
  }
  if (kw) {
    rows = rows.filter(r => {
      const desc = typeDescriptionMap.value[r.dict_code] ?? "";
      return [
        r.dict_code,
        r.dict_name,
        desc,
        r.item_code,
        r.item_name,
        r.remark ?? ""
      ].some(s => s.toLowerCase().includes(kw));
    });
  }
  if (!rows.length) {
    ElMessage.warning("暂无可导出数据");
    return;
  }
  const h = [
    "字典编码",
    "字典名称",
    "说明",
    "取值编码",
    "取值名称",
    "内置",
    "排序",
    "状态",
    "备注",
    "更新时间"
  ];
  const lines = rows.map(r =>
    [
      r.dict_code,
      r.dict_name,
      typeDescriptionMap.value[r.dict_code] ?? "",
      r.item_code,
      r.item_name,
      r.is_builtin ? "是" : "否",
      String(r.sort_no ?? ""),
      r.is_active ? "启用" : "停用",
      r.remark ?? "",
      formatDt(r.updated_at)
    ]
      .map(c => `"${String(c).replace(/"/g, '""')}"`)
      .join(",")
  );
  downloadCsv(
    `字典项_${dayjs().format("YYYY-MM-DD_HHmm")}.csv`,
    [h.join(","), ...lines].join("\r\n")
  );
}

function downloadCsv(filename: string, content: string) {
  const blob = new Blob(["\ufeff" + content], {
    type: "text/csv;charset=utf-8;"
  });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
}

onMounted(async () => {
  restoreUiState();
  await Promise.all([loadDictOptions(), ...(!configuredMenu || activeTab.value === "types" ? [loadTypes()] : [])]);
  if (activeTab.value === "items") await loadAllEntries();
});
</script>

<style scoped lang="scss">
.dict-tabs {
  :deep(.el-tabs__header) {
    margin-bottom: 16px;
  }
}

.tab-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.tab-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
}

.sys-card {
  border-radius: 16px;

  :deep(.el-card__header) {
    padding: 16px 22px;
    border-bottom: none;
  }

  :deep(.el-card__body) {
    padding: 0 22px 22px;
  }
}

.page-header {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  align-items: center;
  justify-content: space-between;
}

.page-title {
  font-size: 30px;
  font-weight: 700;
  color: #111827;
}

.filter-panel {
  padding: 10px 12px 12px;
  background: linear-gradient(180deg, #fbfdff 0%, #f6faff 100%);
  border-radius: 20px;
}

.query-form :deep(.el-form-item__label) {
  font-size: 15px;
  font-weight: 600;
  color: #4b5563;
}

.query-form :deep(.el-form-item) {
  margin-bottom: 0;
}

.dict-filter-row {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr)) auto;
  gap: 16px 14px;
  align-items: start;
}

.dict-items-btn {
  height: 26px;
  padding: 0 10px;
  font-weight: 600;
  border-radius: 999px;
}

.dict-filter-row :deep(.el-input__wrapper),
.dict-filter-row :deep(.el-select__wrapper) {
  height: 48px;
  background: #f2f2f2;
  border-radius: 14px;
  box-shadow: none;
}

.query-actions {
  display: flex;
  gap: 14px;
  align-items: center;
  padding-top: 31px;
}

.search-btn,
.reset-btn {
  min-width: 132px;
  height: 48px;
  font-size: 16px;
  border-radius: 14px;
}

.search-btn {
  color: #409eff;
  background: #fff;
  border-color: #bcdcff;
}

.reset-btn {
  color: #6b7280;
  background: #fff;
  border-color: #d1d5db;
}

.table-panel {
  padding: 10px 0;
  margin-top: 18px;
  background: #fff;
  border: 1px solid #edf2f7;
  border-radius: 18px;
}

.dict-empty-hint {
  padding: 12px 8px 0;
  font-size: 14px;
  color: #94a3b8;
}

.data-table {
  :deep(th.el-table__cell) {
    height: 58px;
    font-weight: 600;
    color: #475569;
    background: #f8fafc;
    border-bottom: 1px solid #e8eef5;
  }

  :deep(td.el-table__cell) {
    height: 72px;
    color: #334155;
  }

  :deep(.el-table__inner-wrapper::before) {
    display: none;
  }
}

.action-text.success {
  margin-right: 10px;
  font-weight: 600;
  color: #22c55e;
  cursor: pointer;
}

.action-text.primary {
  margin-right: 8px;
  font-weight: 600;
  color: #409eff;
  cursor: pointer;
}

.action-text.danger {
  font-weight: 600;
  color: #ef4444;
  cursor: pointer;
}

.table-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 8px 0;
}

.page-size-box {
  display: flex;
  gap: 8px;
  align-items: center;
  color: #6b7280;
}

.page-size-select {
  width: 72px;
}

.btn-cancel {
  color: #b45309;
  background: #fffbeb;
  border-color: #fcd34d;
}

@media (width <= 900px) {
  .dict-filter-row {
    grid-template-columns: 1fr;
  }

  .query-actions {
    padding-top: 0;
  }
}
</style>
