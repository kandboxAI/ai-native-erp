<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { hasPerms } from "@/utils/auth";
import { getHttpErrorMessage } from "@/utils/http";
import { message, actionMessage } from "@/utils/message";
import {
  getManufacturingWarehouses,
  saveManufacturingWarehouse,
  type ManufacturingWarehouse,
} from "@plugins/mes/web/src/api/mesWarehouses";

defineOptions({ name: "MesWarehouseSettings" });
const rows = ref<ManufacturingWarehouse[]>([]);
const types = ref<Record<string, string>>({});
const organizations = ref<{ id: string; org_name: string }[]>([]);
const loading = ref(false),
  saving = ref(false),
  visible = ref(false),
  error = ref("");
const editingId = ref<string>();
const form = reactive({
  org_id: "",
  warehouse_no: "",
  warehouse_name: "",
  warehouse_type_code: "mes_raw",
  is_active: true,
});
async function load() {
  loading.value = true;
  error.value = "";
  try {
    const { data } = await getManufacturingWarehouses();
    rows.value = data.items;
    types.value = data.types;
    organizations.value = data.organizations;
  } catch (cause) {
    error.value = getHttpErrorMessage(cause, "仓库配置读取失败");
  } finally {
    loading.value = false;
  }
}
function edit(row?: ManufacturingWarehouse) {
  editingId.value = row?.id;
  Object.assign(
    form,
    row || {
      org_id: organizations.value.length === 1 ? organizations.value[0].id : "",
      warehouse_no: "",
      warehouse_name: "",
      warehouse_type_code: "mes_raw",
      is_active: true,
    },
  );
  visible.value = true;
}
async function save() {
  if (saving.value) return;
  if (
    !form.org_id ||
    !form.warehouse_no.trim() ||
    !form.warehouse_name.trim()
  ) {
    actionMessage("请填写组织、仓库编号和名称", "warning");
    return;
  }
  saving.value = true;
  try {
    const data = {
      warehouse_name: form.warehouse_name.trim(),
      warehouse_type_code: form.warehouse_type_code,
      is_active: form.is_active,
    };
    await saveManufacturingWarehouse(
      editingId.value,
      editingId.value
        ? data
        : {
            ...data,
            org_id: form.org_id,
            warehouse_no: form.warehouse_no.trim(),
          },
    );
    visible.value = false;
    message("仓库配置已保存", { type: "success" });
    await load();
  } catch (cause) {
    actionMessage(getHttpErrorMessage(cause, "保存失败"));
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
        ><div class="warehouse-header">
          <h2>制造仓库配置</h2>
          <el-button
            v-if="hasPerms('mes:warehouse:manage')"
            type="primary"
            @click="edit()"
            >新增仓库</el-button
          >
        </div></template
      >
      <el-alert
        type="info"
        :closable="false"
        title="原料和在制品仓用于生产领退料；刀具仓用于刀具收发及借还。成品按工单入库和出货，禁止混发。"
      />
      <el-alert v-if="error" type="error" :title="error" :closable="false" />
      <el-table v-loading="loading" :data="rows" row-key="id">
        <el-table-column prop="warehouse_no" label="仓库编号" min-width="140" />
        <el-table-column
          prop="warehouse_name"
          label="仓库名称"
          min-width="160"
        />
        <el-table-column label="组织" min-width="140"
          ><template #default="{ row }">{{
            organizations.find((o) => o.id === row.org_id)?.org_name ||
            row.org_id
          }}</template></el-table-column
        >
        <el-table-column label="用途" min-width="150"
          ><template #default="{ row }">{{
            types[row.warehouse_type_code] || "历史共用仓（只读）"
          }}</template></el-table-column
        >
        <el-table-column label="状态" width="100"
          ><template #default="{ row }"
            ><el-tag :type="row.is_active ? 'success' : 'info'">{{
              row.is_active ? "启用" : "停用"
            }}</el-tag></template
          ></el-table-column
        >
        <el-table-column label="操作" width="100"
          ><template #default="{ row }"
            ><el-button
              v-if="row.can_manage && hasPerms('mes:warehouse:manage')"
              link
              type="primary"
              @click="edit(row as ManufacturingWarehouse)"
              >编辑</el-button
            ></template
          ></el-table-column
        >
      </el-table>
      <el-button class="refresh-button" @click="load">刷新</el-button>
    </el-card>
    <el-dialog
      v-model="visible"
      :title="editingId ? '编辑制造仓库' : '新增制造仓库'"
      width="540px"
      :close-on-click-modal="false"
    >
      <el-form label-width="100px" @submit.prevent="save">
        <el-form-item label="所属组织" required
          ><el-select v-model="form.org_id" :disabled="!!editingId" filterable
            ><el-option
              v-for="org in organizations"
              :key="org.id"
              :value="org.id"
              :label="org.org_name" /></el-select
        ></el-form-item>
        <el-form-item label="仓库编号" required
          ><el-input
            v-model="form.warehouse_no"
            :disabled="!!editingId"
            :maxlength="64"
        /></el-form-item>
        <el-form-item label="仓库名称" required
          ><el-input v-model="form.warehouse_name" :maxlength="128"
        /></el-form-item>
        <el-form-item label="仓库用途" required
          ><el-select v-model="form.warehouse_type_code"
            ><el-option
              v-for="(label, key) in types"
              :key="key"
              :value="key"
              :label="label" /></el-select
        ></el-form-item>
        <el-form-item label="启用"
          ><el-switch v-model="form.is_active"
        /></el-form-item>
      </el-form>
      <p>已有单据不能修改用途；有库存、预留或未记账单据时不能停用。</p>
      <template #footer
        ><el-button @click="visible = false">取消</el-button
        ><el-button type="primary" :loading="saving" @click="save"
          >保存</el-button
        ></template
      >
    </el-dialog>
  </div>
</template>
<style scoped>
.warehouse-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.warehouse-header h2 {
  margin: 0;
}

.refresh-button {
  margin-top: 16px;
}
</style>
