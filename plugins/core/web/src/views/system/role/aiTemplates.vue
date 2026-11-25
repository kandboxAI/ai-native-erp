<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { ElMessage } from "element-plus";
import {
  getAiTemplates,
  saveAiTemplate,
  type PromptTemplate,
  type TemplateConfiguration
} from "@/api/aiContext";

const props = defineProps<{ roleId: string }>();
const configuration = ref<TemplateConfiguration>();
const templates = computed(
  () =>
    configuration.value?.templates.filter(
      row => row.role_id === props.roleId
    ) ?? []
);
const loading = ref(false);
const saving = ref(false);
const managementError = ref("");
const editing = ref<PromptTemplate>();

async function load() {
  loading.value = true;
  managementError.value = "";
  try {
    const response = await getAiTemplates();
    if (response.code !== 0) throw new Error(response.message);
    configuration.value = response.data;
  } catch {
    managementError.value =
      "模板管理不可用，请确认具有本租户全部范围的系统参数管理权限。";
  } finally {
    loading.value = false;
  }
}

function edit(row?: PromptTemplate) {
  editing.value = row
    ? {
        id: row.id,
        template_name: row.template_name,
        role_id: row.role_id,
        instructions: row.instructions,
        is_active: row.is_active
      }
    : {
        template_name: "",
        role_id: props.roleId,
        instructions: "",
        is_active: true
      };
}

async function saveTemplate() {
  const row = editing.value;
  if (!row?.template_name.trim() || !row.instructions.trim() || !row.role_id) {
    ElMessage.warning("请填写模板名称、角色和正文");
    return;
  }
  saving.value = true;
  try {
    const response = await saveAiTemplate(row);
    if (response.code !== 0) throw new Error(response.message);
    editing.value = undefined;
    await load();
    ElMessage.success("模板已保存");
  } catch {
    ElMessage.error("模板保存失败，请检查角色和正文后重试");
  } finally {
    saving.value = false;
  }
}
onMounted(load);
</script>

<template>
  <section v-loading="loading">
    <el-alert
      v-if="managementError"
      class="mt-4"
      :title="managementError"
      type="warning"
      :closable="false"
    />
    <template v-if="configuration && !managementError">
      <h3>AI 工作指导模板</h3>
      <p class="hint">
        当前角色的用户默认使用这些工作指导，也可在个人设置中关闭。模板单独保存，下一轮对话生效。
      </p>
      <el-button data-action="primary" @click="edit()">新增模板</el-button>
      <el-table :data="templates" class="mt-4">
        <el-table-column prop="template_name" label="模板名称" />
        <el-table-column label="状态" width="80"
          ><template #default="{ row }">{{
            row.is_active ? "启用" : "停用"
          }}</template></el-table-column
        >
        <el-table-column label="操作" width="80"
          ><template #default="{ row }"
            ><el-button
              data-action="edit"
              link
              type="primary"
              @click="edit(row as PromptTemplate)"
              >编辑</el-button
            ></template
          ></el-table-column
        >
      </el-table>
    </template>
    <el-button v-if="managementError" link type="primary" @click="load"
      >重试</el-button
    >
    <el-dialog
      append-to-body
      :model-value="!!editing"
      title="角色提示模板"
      width="min(640px, 94vw)"
      @close="editing = undefined"
    >
      <el-form v-if="editing" label-position="top">
        <el-form-item label="模板名称"
          ><el-input v-model="editing.template_name" maxlength="128"
        /></el-form-item>
        <el-form-item label="提示正文"
          ><el-input
            v-model="editing.instructions"
            type="textarea"
            :rows="6"
            maxlength="4000"
            show-word-limit
        /></el-form-item>
        <p class="hint">
          具体班级、课程与任职信息会自动附加，模板只需填写该角色的工作要求。
        </p>
        <el-switch v-model="editing.is_active" active-text="启用" />
      </el-form>
      <template #footer
        ><el-button data-action="neutral" @click="editing = undefined"
          >取消</el-button
        ><el-button
          data-action="primary"
          type="primary"
          :loading="saving"
          @click="saveTemplate"
          >保存</el-button
        ></template
      >
    </el-dialog>
  </section>
</template>

<style scoped>
h3 {
  margin: 20px 0 12px;
  font-size: 16px;
}
.hint {
  margin: 12px 0;
  line-height: 1.7;
  color: var(--el-text-color-secondary);
}
</style>
