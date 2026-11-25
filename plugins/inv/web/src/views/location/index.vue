<script setup lang="ts">
import { actionMessage } from "@/utils/message";
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { hasPerms } from "@/utils/auth";
import { getHttpErrorMessage } from "@/utils/http";
import {
  listLocations,
  locationMeta,
  saveLocation,
  deleteLocation,
  type LocationItem,
  type LocationBody,
} from "../../api/invLocation";
import { parseCoordinates } from "../../utils/locationCoordinates";
defineOptions({ name: "UnifiedLocations" });
const loading = ref(false),
  saving = ref(false),
  visible = ref(false);
const rows = ref<LocationItem[]>([]);
const meta = ref<Awaited<ReturnType<typeof locationMeta>>["data"]>({
  organizations: [],
  default_org_id: null,
  can_change_org: false,
  location_types: [],
  coordinate_systems: [],
});
const editing = ref<LocationItem | null>(null);
const query = reactive({
  org_id: "",
  keyword: "",
  status: "",
  page: 1,
  page_size: 20,
});
const form = reactive<LocationBody>({
  org_id: "",
  location_name: "",
  location_type_code: "room",
  latitude: null,
  longitude: null,
  coordinate_system_code: "gcj02",
  location_description: "",
  sort_no: 0,
  is_active: true,
  remark: "",
});
const coordinateText = ref("");
const canManage = computed(() => hasPerms("md_location:manage"));
const pickerUrl = "https://www.amap.com/ssr/coordinate-picker";
const filtered = computed(() =>
  rows.value.filter(
    (row) =>
      (!query.keyword ||
        row.location_name
          .toLowerCase()
          .includes(query.keyword.toLowerCase())) &&
      (!query.status || String(row.is_active) === query.status),
  ),
);
const paged = computed(() =>
  filtered.value.slice(
    (query.page - 1) * query.page_size,
    query.page * query.page_size,
  ),
);
const orgName = (id: string) =>
  meta.value.organizations.find((item) => item.id === id)?.org_name || "—";
const typeName = (code: string) =>
  meta.value.location_types.find((item) => item.value === code)?.label || code;
async function load() {
  loading.value = true;
  try {
    rows.value = (await listLocations(query.org_id)).data.items;
    query.page = 1;
  } catch (error) {
    ElMessage.error(getHttpErrorMessage(error));
  } finally {
    loading.value = false;
  }
}
function resetQuery() {
  Object.assign(query, { org_id: "", keyword: "", status: "", page: 1 });
  void load();
}
async function changeOrg() {
  await load();
}
function open(row?: LocationItem) {
  editing.value = row || null;
  Object.assign(
    form,
    row
      ? {
          org_id: row.org_id,
          location_name: row.location_name,
          location_type_code: row.location_type_code,
          latitude: Number(row.latitude),
          longitude: Number(row.longitude),
          coordinate_system_code: row.coordinate_system_code,
          location_description: row.location_description,
          sort_no: row.sort_no,
          is_active: row.is_active,
          remark: row.remark,
        }
      : {
          org_id:
            query.org_id ||
            meta.value.default_org_id ||
            (meta.value.organizations.length === 1
              ? meta.value.organizations[0].id
              : "") ||
            "",
          location_name: "",
          location_type_code: "room",
          latitude: null,
          longitude: null,
          coordinate_system_code: "gcj02",
          location_description: "",
          sort_no: 0,
          is_active: true,
          remark: "",
        },
  );
  coordinateText.value = "";
  visible.value = true;
}
function applyCoordinates() {
  try {
    Object.assign(form, parseCoordinates(coordinateText.value));
    form.coordinate_system_code = "gcj02";
  } catch (error) {
    actionMessage((error as Error).message, "warning");
  }
}
function pasteCoordinates(event: ClipboardEvent) {
  coordinateText.value = event.clipboardData?.getData("text") || "";
  applyCoordinates();
}
function resetCoordinates() {
  form.longitude = null;
  form.latitude = null;
  form.coordinate_system_code = "gcj02";
}
async function save() {
  if (!form.org_id || !form.location_name.trim())
    return ElMessage.warning("请选择所属组织并填写位置名称");
  if (form.coordinate_system_code !== "gcj02")
    return ElMessage.warning(
      "原坐标不是高德坐标，请重新选点或录入 GCJ-02 经纬度",
    );
  if (
    form.latitude == null ||
    form.longitude == null ||
    !Number.isFinite(form.latitude) ||
    !Number.isFinite(form.longitude)
  )
    return ElMessage.warning("每个位置都必须填写经纬度");
  saving.value = true;
  try {
    await saveLocation(
      { ...form },
      editing.value?.id,
      editing.value?.version_no,
    );
    visible.value = false;
    ElMessage.success("位置已保存");
    await load();
  } catch (error) {
    ElMessage.error(getHttpErrorMessage(error));
  } finally {
    saving.value = false;
  }
}
async function remove(row: LocationItem) {
  try {
    await ElMessageBox.confirm(
      `删除位置“${row.location_name}”？被业务引用的位置请使用停用功能。`,
      "删除位置",
      { type: "warning", confirmButtonClass: "app-button-danger" },
    );
  } catch {
    return;
  }
  try {
    await deleteLocation(row.id, row.version_no);
    ElMessage.success("位置已删除");
    await load();
  } catch (error) {
    ElMessage.error(getHttpErrorMessage(error));
  }
}
onMounted(async () => {
  try {
    meta.value = (await locationMeta()).data;
    await load();
  } catch (error) {
    ElMessage.error(getHttpErrorMessage(error));
  }
});
</script>
<template>
  <ReListPresentation
    :filters="{
      org_id: query.org_id || null,
      is_active: query.status || null,
    }"
  >
    <div class="location-page list-page list-presentation-container">
      <ReListHeading data-list-key="location-master-v1">
        <p>集中维护位置名称与经纬度，供资产、仓库和巡查共同选用。</p>
      </ReListHeading>
      <section v-loading="loading" class="list-query-panel">
        <el-form inline class="list-filters" @submit.prevent="load">
          <el-form-item label="所属组织">
            <el-select v-model="query.org_id" clearable @change="changeOrg">
              <el-option
                v-for="org in meta.organizations"
                :key="org.id"
                :value="org.id"
                :label="org.org_name"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="位置名称">
            <el-input
              v-model="query.keyword"
              clearable
              placeholder="请输入位置名称"
              @input="query.page = 1"
              @keyup.enter="load"
            />
          </el-form-item>
          <el-form-item label="状态">
            <el-select
              v-model="query.status"
              clearable
              @change="query.page = 1"
            >
              <el-option label="启用" value="true" />
              <el-option label="停用" value="false" />
            </el-select>
          </el-form-item>
          <el-form-item class="list-query-actions">
            <el-button data-list-query="search" type="primary" @click="load"
              >查询</el-button
            >
            <el-button data-list-query="reset" @click="resetQuery"
              >重置</el-button
            >
          </el-form-item>
        </el-form>
        <div class="location-list">
          <ReListTable
            :list-heading="false"
            list-key="location-master-v1"
            :list-refresh="load"
            :data="paged"
            stripe
            row-key="id"
          >
            <el-table-column
              prop="location_name"
              label="位置名称"
              min-width="200"
              fixed="left"
            >
              <template #default="{ row }">
                <ReListIdentity :primary="row.location_name" />
              </template>
            </el-table-column>
            <el-table-column
              prop="location_type_code"
              label="类型"
              min-width="100"
            >
              <template #default="{ row }">{{
                typeName(row.location_type_code)
              }}</template>
            </el-table-column>
            <el-table-column prop="org_id" label="组织" min-width="130">
              <template #default="{ row }">{{ orgName(row.org_id) }}</template>
            </el-table-column>
            <el-table-column
              prop="longitude"
              label="经度 / 纬度"
              min-width="190"
            >
              <template #default="{ row }">
                <div>{{ row.longitude }}, {{ row.latitude }}</div>
                <div class="location-coordinate-system">
                  {{ row.coordinate_system_code.toUpperCase() }}
                </div>
              </template>
            </el-table-column>
            <el-table-column prop="is_active" label="状态" min-width="110">
              <template #default="{ row }">
                <el-tag :type="row.is_active ? 'success' : 'info'">{{
                  row.is_active ? "启用" : "停用"
                }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column
              v-if="canManage"
              label="操作"
              width="130"
              fixed="right"
            >
              <template #default="{ row }">
                <el-button
                  data-list-action="edit"
                  link
                  type="primary"
                  @click="open(row as LocationItem)"
                  >编辑</el-button
                >
                <el-button
                  data-list-action="delete"
                  link
                  type="danger"
                  @click="remove(row as LocationItem)"
                  >删除</el-button
                >
              </template>
            </el-table-column>
            <template #list-actions>
              <el-button
                v-if="canManage"
                data-list-action="create"
                type="primary"
                @click="open()"
                >新增位置</el-button
              >
            </template>
            <template #list-pagination>
              <ReListPagination
                v-model:current-page="query.page"
                v-model:page-size="query.page_size"
                :total="filtered.length"
              />
            </template>
          </ReListTable>
        </div>
      </section>
      <el-dialog
        v-model="visible"
        :title="editing ? '编辑位置' : '新增位置'"
        width="min(680px, calc(100vw - 32px))"
        align-center
      >
        <el-form
          class="location-form"
          label-width="100px"
          @submit.prevent="save"
        >
          <el-form-item label="所属组织" required
            ><el-select
              v-model="form.org_id"
              :disabled="
                (!!editing && !meta.can_change_org) ||
                meta.organizations.length === 1
              "
              ><el-option
                v-for="org in meta.organizations"
                :key="org.id"
                :value="org.id"
                :label="org.org_name"
            /></el-select>
            <span v-if="editing && meta.can_change_org" class="muted">
              未被仓库、资产或巡查引用的位置可调整所属组织。
            </span>
          </el-form-item>
          <el-form-item label="位置名称" required
            ><el-input
              v-model="form.location_name"
              maxlength="128"
              placeholder="例如：一号教学楼301室"
          /></el-form-item>
          <el-form-item label="位置类型" required
            ><el-select v-model="form.location_type_code"
              ><el-option
                v-for="type in meta.location_types"
                :key="type.value"
                :value="type.value"
                :label="type.label" /></el-select
          ></el-form-item>
          <el-form-item label="地图选点"
            ><div class="coordinate-panel">
              <el-link
                :href="pickerUrl"
                target="_blank"
                rel="noopener noreferrer"
                type="primary"
                >打开高德地图选点 ↗</el-link
              >
              <p class="muted">
                点击地图复制坐标，按“经度,纬度”粘贴。统一使用高德/微信坐标（GCJ-02）。
              </p>
              <p
                v-if="form.coordinate_system_code !== 'gcj02'"
                role="alert"
                class="coordinate-warning"
              >
                原坐标为
                {{
                  form.coordinate_system_code.toUpperCase()
                }}，请重新选点或录入高德经纬度后保存。
                <el-button
                  link
                  type="primary"
                  data-action="neutral"
                  @click="resetCoordinates"
                  >重新录入高德坐标</el-button
                >
              </p>
              <div class="coordinate-entry">
                <el-input
                  v-model="coordinateText"
                  aria-label="地图坐标（经度,纬度）"
                  placeholder="经度,纬度"
                  @paste.prevent="pasteCoordinates"
                  @keyup.enter.stop="applyCoordinates"
                /><el-button data-action="primary" @click="applyCoordinates"
                  >填入坐标</el-button
                >
              </div>
            </div></el-form-item
          >
          <div class="form-grid">
            <el-form-item label="经度" required
              ><el-input-number
                v-model="form.longitude"
                :min="-180"
                :max="180"
                :precision="7"
                :controls="false" /></el-form-item
            ><el-form-item label="纬度" required
              ><el-input-number
                v-model="form.latitude"
                :min="-90"
                :max="90"
                :precision="7"
                :controls="false"
            /></el-form-item>
          </div>
          <el-form-item label="位置说明"
            ><el-input v-model="form.location_description" maxlength="500"
          /></el-form-item>
          <div class="form-grid">
            <el-form-item label="排序"
              ><el-input-number
                v-model="form.sort_no"
                :min="0"
                :max="999999" /></el-form-item
            ><el-form-item label="启用"
              ><el-switch v-model="form.is_active"
            /></el-form-item>
          </div>
          <el-form-item label="备注"
            ><el-input v-model="form.remark" type="textarea" maxlength="1000"
          /></el-form-item>
        </el-form>
        <template #footer
          ><el-button data-action="neutral" @click="visible = false"
            >取消</el-button
          ><el-button
            data-action="primary"
            type="primary"
            :loading="saving"
            @click="save"
            >保存</el-button
          ></template
        >
      </el-dialog>
    </div>
  </ReListPresentation>
</template>

<style scoped>
.location-page,
.location-list {
  min-width: 0;
}

.location-coordinate-system,
.muted {
  font-size: 12px;
  font-weight: normal;
  line-height: 1.8;
  color: var(--el-text-color-secondary);
}

.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
}

.coordinate-panel {
  width: 100%;
  padding: 12px;
  background: var(--el-fill-color-light);
  border-radius: 6px;
}

.coordinate-warning {
  color: var(--el-color-warning-dark-2);
}

.coordinate-entry {
  display: flex;
  gap: 8px;
  margin: 8px 0;
}

.location-form :deep(.el-select),
.location-form :deep(.el-input-number) {
  width: 100%;
}

@media (max-width: 800px) {
  .form-grid {
    grid-template-columns: 1fr;
  }
}
</style>
