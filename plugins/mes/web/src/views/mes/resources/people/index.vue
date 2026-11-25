<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import ActionButton from "@/components/ActionButton/index.vue";
import ListPagination from "@/components/ListPagination/index.vue";
import { hasPerms } from "@/utils/auth";
import { getHttpErrorMessage } from "@/utils/http";
import { message, actionMessage } from "@/utils/message";
import RemoteSelect from "../../components/RemoteSelect.vue";
import {
  resourcePage,
  resourceDetail,
  saveResource,
  resourceOrganizations,
  resourceProcesses,
  type ResourceRow,
  type Qualification,
} from "@plugins/mes/web/src/api/mesScheduleResources";
defineOptions({ name: "MesProductionPeople" });
const query = reactive({
  org_id: "",
  keyword: "",
  process_id: "",
  page: 1,
  page_size: 20,
});
const rows = ref<ResourceRow[]>([]),
  total = ref(0),
  busy = ref(false),
  error = ref("");
const editing = ref(false),
  person = ref<ResourceRow>();
const form = reactive({
  org_id: "",
  person_no: "",
  full_name: "",
  job_title_snapshot: "",
  is_active: true,
});
const canManage = computed(() => hasPerms("mes:schedule_resource:manage"));
const skillVisible = ref(false),
  skill = ref<Qualification>();
const qualification = reactive({
  process_id: "",
  valid_from: new Date(),
  valid_to: undefined as Date | undefined,
  is_active: true,
});
const time = (value?: string | null) =>
  value
    ? new Date(value).toLocaleString("zh-CN", { hour12: false })
    : "持续有效";
async function load() {
  busy.value = true;
  error.value = "";
  try {
    const result = await resourcePage("people", {
      ...query,
      org_id: query.org_id || undefined,
      process_id: query.process_id || undefined,
    });
    rows.value = result.items;
    total.value = result.total;
  } catch (e) {
    error.value = getHttpErrorMessage(e, "读取生产人员失败");
  } finally {
    busy.value = false;
  }
}
async function open(row?: ResourceRow) {
  error.value = "";
  busy.value = true;
  try {
    person.value = row ? await resourceDetail("people", row.id) : undefined;
    Object.assign(form, {
      org_id: person.value?.org_id || query.org_id,
      person_no: person.value?.person_no || "",
      full_name: person.value?.full_name || "",
      job_title_snapshot: person.value?.job_title_snapshot || "",
      is_active: person.value?.is_active ?? true,
    });
    editing.value = true;
  } catch (e) {
    error.value = getHttpErrorMessage(e, "读取人员失败");
  } finally {
    busy.value = false;
  }
}
async function save() {
  if (!form.org_id || !form.person_no.trim() || !form.full_name.trim()) {
    actionMessage("请填写组织、人员编号和姓名", "warning");
    return;
  }
  busy.value = true;
  try {
    await saveResource(
      person.value ? `people/${person.value.id}` : "people",
      { ...form, version_no: person.value?.version_no },
      !!person.value,
    );
    message("保存成功", { type: "success" });
    editing.value = false;
    await load();
  } catch (e) {
    actionMessage(getHttpErrorMessage(e, "保存失败"));
  } finally {
    busy.value = false;
  }
}
function openSkill(row?: Qualification) {
  skill.value = row;
  Object.assign(qualification, {
    process_id: row?.process_id || "",
    valid_from: row ? new Date(row.valid_from) : new Date(),
    valid_to: row?.valid_to ? new Date(row.valid_to) : undefined,
    is_active: row?.is_active ?? true,
  });
  error.value = "";
  skillVisible.value = true;
}
async function saveSkill() {
  if (!person.value || !qualification.process_id || !qualification.valid_from) {
    actionMessage("请选择工艺和生效时间", "warning");
    return;
  }
  busy.value = true;
  try {
    await saveResource(
      `people/${person.value.id}/qualifications${skill.value ? `/${skill.value.id}` : ""}`,
      {
        org_id: person.value.org_id,
        version_no: skill.value?.version_no,
        process_id: qualification.process_id,
        valid_from: qualification.valid_from.toISOString(),
        valid_to: qualification.valid_to?.toISOString() || null,
        is_active: qualification.is_active,
      },
      !!skill.value,
    );
    person.value = await resourceDetail("people", person.value.id);
    skillVisible.value = false;
    message("技能资格已保存", { type: "success" });
  } catch (e) {
    actionMessage(getHttpErrorMessage(e, "保存技能失败"));
  } finally {
    busy.value = false;
  }
}
onMounted(load);
</script>
<template>
  <div v-loading="busy" class="mes-page resource-people">
    <div class="page-heading">
      <div>
        <h2>
          {{
            editing
              ? person
                ? `${person.full_name} · 生产人员与技能`
                : "新增生产人员"
              : "生产人员与技能"
          }}
        </h2>
        <p class="muted">
          人员技能决定可做的工艺；设备由工艺能力匹配。生产身份与登录账号分别管理。
        </p>
      </div>
      <el-button
        v-if="editing"
        @click="
          editing = false;
          load();
        "
        >返回列表</el-button
      ><ActionButton v-else-if="canManage" intent="create" @click="open()"
        >新增生产人员</ActionButton
      >
    </div>
    <el-alert
      v-if="error"
      :title="error"
      type="error"
      :closable="false"
      show-icon
    />
    <template v-if="!editing">
      <el-card shadow="never"
        ><el-form
          inline
          class="erp-query-form"
          @submit.prevent="
            query.page = 1;
            load();
          "
          ><el-form-item label="组织"
            ><RemoteSelect
              v-model="query.org_id"
              :load-options="resourceOrganizations"
              placeholder="选择组织" /></el-form-item
          ><el-form-item label="人员"
            ><el-input
              v-model="query.keyword"
              clearable
              placeholder="姓名或人员编号" /></el-form-item
          ><el-form-item label="工艺能力"
            ><RemoteSelect
              v-model="query.process_id"
              :disabled="!query.org_id"
              :context-key="query.org_id"
              :load-options="
                (keyword) => resourceProcesses(query.org_id, keyword)
              "
              placeholder="按已生效技能筛选" /></el-form-item
          ><el-form-item
            ><el-button type="primary" native-type="submit"
              >查询</el-button
            ></el-form-item
          ></el-form
        >
        <el-table :data="rows" border
          ><el-table-column
            prop="person_no"
            label="人员编号"
            min-width="180"
          /><el-table-column
            prop="full_name"
            label="姓名"
            min-width="150"
          /><el-table-column
            prop="job_title_snapshot"
            label="职务"
            min-width="180"
          /><el-table-column label="状态" width="100"
            ><template #default="{ row }"
              ><el-tag :type="row.is_active ? 'success' : 'info'">{{
                row.is_active ? "启用" : "停用"
              }}</el-tag></template
            ></el-table-column
          ><el-table-column label="操作" width="160"
            ><template #default="{ row }"
              ><el-button
                link
                type="primary"
                @click="open(row as ResourceRow)"
                >{{
                  canManage ? "维护人员与技能" : "查看人员与技能"
                }}</el-button
              ></template
            ></el-table-column
          ></el-table
        >
        <ListPagination
          v-model:current-page="query.page"
          v-model:page-size="query.page_size"
          :total="total"
          @current-change="load"
          @size-change="
            query.page = 1;
            load();
          "
        />
      </el-card>
    </template>
    <template v-else>
      <el-card shadow="never"
        ><el-form
          :disabled="!canManage"
          label-position="top"
          @submit.prevent="save"
          ><div class="resource-fields">
            <el-form-item label="所属组织" required
              ><RemoteSelect
                v-model="form.org_id"
                :disabled="!!person"
                :load-options="resourceOrganizations"
                placeholder="选择组织" /></el-form-item
            ><el-form-item label="人员编号" required
              ><el-input
                v-model="form.person_no"
                maxlength="64" /></el-form-item
            ><el-form-item label="姓名" required
              ><el-input
                v-model="form.full_name"
                :disabled="!!person"
                maxlength="128" /></el-form-item
            ><el-form-item label="职务"
              ><el-input
                v-model="form.job_title_snapshot"
                maxlength="128" /></el-form-item
            ><el-form-item label="启用"
              ><el-switch v-model="form.is_active"
            /></el-form-item>
          </div>
          <p v-if="!person" class="muted">
            建立公共自然人及生产身份，不创建登录账号。同名人员会提示管理员核对，避免重复建档。
          </p>
          <div v-if="canManage" class="erp-form-actions">
            <el-button @click="editing = false">取消</el-button
            ><el-button type="primary" native-type="submit">保存人员</el-button>
          </div></el-form
        ></el-card
      >
      <el-card v-if="person" shadow="never"
        ><div class="page-heading">
          <h3>工艺技能资格</h3>
          <ActionButton v-if="canManage" intent="create" @click="openSkill()"
            >添加技能</ActionButton
          >
        </div>
        <el-table :data="person.qualifications" border
          ><el-table-column
            prop="process_name"
            label="工艺"
            min-width="180"
          /><el-table-column label="生效时间" min-width="190"
            ><template #default="{ row }">{{
              time(row.valid_from)
            }}</template></el-table-column
          ><el-table-column label="失效时间" min-width="190"
            ><template #default="{ row }">{{
              time(row.valid_to)
            }}</template></el-table-column
          ><el-table-column label="状态" width="100"
            ><template #default="{ row }"
              ><el-tag :type="row.is_active ? 'success' : 'info'">{{
                row.is_active ? "启用" : "停用"
              }}</el-tag></template
            ></el-table-column
          ><el-table-column v-if="canManage" label="操作" width="100"
            ><template #default="{ row }"
              ><el-button
                link
                type="primary"
                @click="openSkill(row as Qualification)"
                >编辑</el-button
              ></template
            ></el-table-column
          ></el-table
        ></el-card
      >
    </template>
    <el-dialog
      v-model="skillVisible"
      title="工艺技能资格"
      width="560px"
      :close-on-click-modal="false"
      ><el-form label-position="top" :disabled="busy"
        ><el-form-item label="工艺" required
          ><RemoteSelect
            v-model="qualification.process_id"
            :disabled="!!skill"
            :load-options="(keyword) => resourceProcesses(form.org_id, keyword)"
            :initial-option="
              skill
                ? { value: skill.process_id, label: skill.process_name }
                : undefined
            "
            placeholder="选择明确确认的工艺能力" /></el-form-item
        ><el-form-item label="生效时间" required
          ><el-date-picker
            v-model="qualification.valid_from"
            type="datetime" /></el-form-item
        ><el-form-item label="失效时间（不填为持续有效）"
          ><el-date-picker
            v-model="qualification.valid_to"
            type="datetime"
            clearable /></el-form-item
        ><el-form-item label="启用"
          ><el-switch v-model="qualification.is_active" /></el-form-item
        ><el-alert
          v-if="error"
          type="error"
          :title="error"
          :closable="false" /></el-form
      ><template #footer
        ><el-button :disabled="busy" @click="skillVisible = false"
          >取消</el-button
        ><el-button type="primary" :loading="busy" @click="saveSkill"
          >保存技能</el-button
        ></template
      ></el-dialog
    >
  </div>
</template>
<style scoped>
.resource-people :deep(.el-card),
.resource-people > :deep(.el-alert) {
  margin-bottom: 20px;
}

.resource-fields {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 0 24px;
}

.resource-people :deep(.el-select) {
  min-width: 200px;
}
</style>
