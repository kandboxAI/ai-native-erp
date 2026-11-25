<script setup lang="ts">
import ListPagination from "@/components/ListPagination/index.vue";
import { onMounted, reactive, ref } from "vue";
import dayjs from "dayjs";
import { hasPerms } from "@/utils/auth";
import { getHttpErrorMessage } from "@/utils/http";
import { message, actionMessage } from "@/utils/message";
import {
  getSupplierPrices,
  saveSupplierPrice,
  priceOptions,
  priceOrganizations,
  type SupplierPrice,
} from "@plugins/mes/web/src/api/mesArchives";
import RemoteSelect from "./RemoteSelect.vue";

const rows = ref<SupplierPrice[]>([]),
  total = ref(0),
  page = ref(1),
  keyword = ref("");
const loading = ref(false),
  saving = ref(false),
  visible = ref(false),
  error = ref("");
const editing = ref<SupplierPrice>();
const empty = () => ({
  org_id: "",
  supplier_id: "",
  item_id: "",
  currency_code: "CNY",
  unit_price: "",
  valid_from: dayjs().format("YYYY-MM-DD"),
  valid_to: "",
  is_active: true,
  note: "",
});
const form = reactive(empty());
let request = 0;
async function load() {
  const current = ++request;
  loading.value = true;
  error.value = "";
  try {
    const { data } = await getSupplierPrices({
      keyword: keyword.value,
      page: page.value,
      page_size: 20,
    });
    if (current === request) {
      rows.value = data.items;
      total.value = data.total;
    }
  } catch (cause) {
    if (current === request)
      error.value = getHttpErrorMessage(cause, "采购价读取失败");
  } finally {
    if (current === request) loading.value = false;
  }
}
function search() {
  page.value = 1;
  load();
}
function edit(row?: SupplierPrice) {
  editing.value = row;
  Object.assign(
    form,
    empty(),
    row || {},
    row
      ? { unit_price: String(row.unit_price), valid_to: row.valid_to || "" }
      : {},
  );
  visible.value = true;
}
async function save() {
  if (saving.value) return;
  if (
    !form.org_id ||
    !form.supplier_id ||
    !form.item_id ||
    !form.valid_from ||
    !/^\d+(\.\d{1,2})?$/.test(form.unit_price)
  ) {
    actionMessage("请选择组织、供应商、货品、生效日期，并填写非负单价（最多两位小数）", "warning");
    return;
  }
  if (form.valid_to && form.valid_to <= form.valid_from) {
    actionMessage("失效日期必须晚于生效日期", "warning");
    return;
  }
  saving.value = true;
  try {
    const data = {
      org_id: form.org_id,
      supplier_id: form.supplier_id,
      item_id: form.item_id,
      currency_code: form.currency_code.trim(),
      unit_price: form.unit_price,
      valid_from: form.valid_from,
      valid_to: form.valid_to || null,
      is_active: form.is_active,
      note: form.note || null,
      ...(editing.value ? { version_no: editing.value.version_no } : {}),
    };
    await saveSupplierPrice(editing.value?.id, data);
    visible.value = false;
    message("采购价已保存", { type: "success" });
    await load();
  } catch (cause) {
    actionMessage(getHttpErrorMessage(cause, "采购价保存失败"));
  } finally {
    saving.value = false;
  }
}
onMounted(load);
</script>
<template>
  <div class="sys-page sys-module">
    <el-card shadow="never">
      <template #header
        ><div class="price-header">
          <h2>采购价格表</h2>
          <el-button
            v-if="hasPerms('inventory_supplier_price:manage')"
            type="primary"
            @click="edit()"
            >新增采购价</el-button
          >
        </div></template
      >
      <el-form inline @submit.prevent="search"
        ><el-form-item
          ><el-input
            v-model="keyword"
            placeholder="供应商 / 货品编号或名称"
            clearable
            @keyup.enter="search" /></el-form-item
        ><el-form-item
          ><el-button type="primary" @click="search">查询</el-button
          ><el-button
            @click="
              keyword = '';
              search();
            "
            >重置</el-button
          ></el-form-item
        ></el-form
      >
      <el-alert v-if="error" type="error" :title="error" :closable="false" />
      <el-table v-loading="loading" :data="rows" row-key="id"
        ><el-table-column
          prop="supplier_no"
          label="供应商编号"
          min-width="130"
        /><el-table-column
          prop="supplier_name"
          label="供应商"
          min-width="160"
        /><el-table-column
          prop="item_no"
          label="货品编号"
          min-width="140"
        /><el-table-column
          prop="item_name"
          label="货品"
          min-width="160"
        /><el-table-column
          prop="unit_code"
          label="基本单位"
          width="100"
        /><el-table-column
          prop="currency_code"
          label="币种"
          width="80"
        /><el-table-column
          prop="unit_price"
          label="单价"
          width="110"
        /><el-table-column
          prop="valid_from"
          label="生效日期"
          width="120"
        /><el-table-column
          prop="valid_to"
          label="失效日期（不含）"
          width="150"
        /><el-table-column label="状态" width="90"
          ><template #default="{ row }"
            ><el-tag :type="row.is_active ? 'success' : 'info'">{{
              row.is_active ? "启用" : "停用"
            }}</el-tag></template
          ></el-table-column
        ><el-table-column
          v-if="hasPerms('inventory_supplier_price:manage')"
          label="操作"
          width="90"
          ><template #default="{ row }"
            ><el-button link type="primary" @click="edit(row as SupplierPrice)"
              >编辑</el-button
            ></template
          ></el-table-column
        ></el-table
      >
      <ListPagination
        v-model:current-page="page"
        :page-size="20"
        :total="total"
        layout="total, prev, pager, next"
        @current-change="load"
      />
      <el-dialog
        v-model="visible"
        :title="editing ? '编辑采购价' : '新增采购价'"
        width="640px"
        :close-on-click-modal="false"
        destroy-on-close
      >
        <el-form label-width="100px" @submit.prevent="save">
          <el-form-item label="组织" required
            ><RemoteSelect
              v-model="form.org_id"
              :load-options="priceOrganizations"
              :disabled="!!editing"
              :auto-select-single="true"
              :initial-option="
                editing
                  ? { value: editing.org_id, label: '所属组织' }
                  : undefined
              "
              placeholder="选择组织"
          /></el-form-item>
          <el-form-item label="供应商" required
            ><RemoteSelect
              v-model="form.supplier_id"
              :load-options="(value) => priceOptions('suppliers', value)"
              :initial-option="
                editing
                  ? {
                      value: editing.supplier_id,
                      label: editing.supplier_name || editing.supplier_id,
                    }
                  : undefined
              "
              placeholder="按编号或名称搜索"
          /></el-form-item>
          <el-form-item label="货品" required
            ><RemoteSelect
              v-model="form.item_id"
              :load-options="(value) => priceOptions('items', value)"
              :initial-option="
                editing
                  ? {
                      value: editing.item_id,
                      label: editing.item_name || editing.item_id,
                    }
                  : undefined
              "
              placeholder="按编号或名称搜索"
          /></el-form-item>
          <el-form-item label="币种" required
            ><el-input
              v-model="form.currency_code"
              :maxlength="64"
              placeholder="CNY" /></el-form-item
          ><el-form-item label="基本单位单价" required
            ><el-input
              v-model="form.unit_price"
              placeholder="最多两位小数" /></el-form-item
          ><el-form-item label="生效日期" required
            ><el-date-picker
              v-model="form.valid_from"
              value-format="YYYY-MM-DD" /></el-form-item
          ><el-form-item label="失效日期"
            ><el-date-picker
              v-model="form.valid_to"
              value-format="YYYY-MM-DD"
              placeholder="不含此日；不填表示持续有效" /></el-form-item
          ><el-form-item label="启用"
            ><el-switch v-model="form.is_active" /></el-form-item
          ><el-form-item label="说明"
            ><el-input v-model="form.note" type="textarea" :maxlength="1000"
          /></el-form-item> </el-form
        ><small
          >单价按货品基本单位维护；相同供应商、货品和币种的启用价格不能在同一组织内重叠生效。保存不会自动改写库存或历史单据价格。</small
        >
        <template #footer
          ><el-button @click="visible = false">取消</el-button
          ><el-button type="primary" :loading="saving" @click="save"
            >保存</el-button
          ></template
        >
      </el-dialog>
    </el-card>
  </div>
</template>
<style scoped>
.price-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
h2 {
  margin: 0;
}
small {
  color: var(--el-text-color-secondary);
}
.el-pagination {
  margin-top: 20px;
}
</style>
