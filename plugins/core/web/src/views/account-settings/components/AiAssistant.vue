<script setup lang="ts">
import { defineAsyncComponent, onMounted, ref } from "vue";
import deployedViews from "virtual:deployed-views";
import { ElMessage } from "element-plus";
import { useRouter } from "vue-router";
import { hasPerms } from "@/utils/auth";
import {
  getAiContext,
  saveAiInstructions,
  saveMyAiTemplate,
  type AiContext,
  type PersonalRoleTemplate
} from "@/api/aiContext";

const context = ref<AiContext>();
const router = useRouter();
const instructions = ref("");
const loading = ref(false);
const saving = ref(false);
const error = ref("");
const changingTemplate = ref("");
const viewingTemplate = ref<PersonalRoleTemplate>();
// 通过部署页面表加载可选知识插件，纯底座不依赖插件源码。
const responsibilitiesLoader = deployedViews["/src/views/knowledge/components/PositionResponsibilities.vue"];
const PositionResponsibilities = responsibilitiesLoader
  ? defineAsyncComponent(responsibilitiesLoader)
  : undefined;
async function load() {
  loading.value = true;
  error.value = "";
  try {
    const result = await getAiContext();
    if (result.code !== 0) throw new Error(result.message);
    context.value = result.data;
    instructions.value = result.data.instructions;
  } catch {
    error.value = "AI 配置加载失败，请确认服务及数据库已更新后重试。";
  } finally {
    loading.value = false;
  }
}

async function savePersonal() {
  saving.value = true;
  try {
    const result = await saveAiInstructions(instructions.value);
    if (result.code !== 0) throw new Error(result.message);
    context.value = result.data;
    instructions.value = result.data.instructions;
    ElMessage.success("已保存，下一轮对话生效");
  } catch {
    ElMessage.error("个人偏好保存失败，请重试");
  } finally {
    saving.value = false;
  }
}

async function toggleTemplate(row: PersonalRoleTemplate, isActive: boolean) {
  changingTemplate.value = row.id;
  try {
    const response = await saveMyAiTemplate(row.id, isActive);
    if (response.code !== 0) throw new Error(response.message);
    // 仅刷新生效结果，保留尚未保存的个人偏好草稿。
    context.value = response.data;
    ElMessage.success("已保存，下一轮对话生效");
  } catch {
    ElMessage.error("模板开关保存失败，请刷新确认模板仍可用后重试");
  } finally {
    changingTemplate.value = "";
  }
}

onMounted(load);
</script>

<template>
  <section v-loading="loading" class="ai-settings">
    <h2>AI 助手</h2>
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <el-button data-action="primary" v-if="error" class="mt-4" @click="load"
      >重试</el-button
    >
    <template v-if="context && !error">
      <p class="hint">
        生效顺序：系统基础规则 → 角色模板 → 我的身份信息 → 岗位知识 →
        个人偏好。个人偏好优先决定回答风格、长度和格式；身份及权限以 ERP
        实际配置为准。
      </p>
      <h3>我的身份信息</h3>
      <p v-if="context.role_names.length">
        角色：{{ context.role_names.join("、") }}
      </p>
      <ul v-if="context.facts.length">
        <li v-for="fact in context.facts" :key="fact">{{ fact }}</li>
      </ul>
      <el-empty
        v-else-if="!context.role_names.length"
        description="暂无身份信息"
        :image-size="60"
      />
      <h3>我的岗位知识</h3>
      <p class="hint">查看岗位职责，维护本岗位的共享资料。</p>
      <el-table v-if="context.position_knowledge?.length" :data="context.position_knowledge">
        <el-table-column prop="position_name" label="岗位" />
        <el-table-column prop="knowledge_base_name" label="共享知识库" />
        <el-table-column label="岗位说明"><template #default="{ row }">{{ row.version_no ? `已加载正式版 v${row.version_no}` : '未加载可读的正式说明' }}</template></el-table-column>
        <el-table-column label="操作"><template #default="{ row }">
          <el-button v-if="router.hasRoute('KnowledgeAuthorization')" type="primary" link @click="router.push({ name: 'KnowledgeAuthorization', query: { knowledge_base_id: row.knowledge_base_id } })">查看岗位知识</el-button>
          <span v-else>可在 DSH 中按任务检索</span>
        </template></el-table-column>
      </el-table>
      <template v-if="PositionResponsibilities && context.position_knowledge?.length">
        <component
          :is="PositionResponsibilities"
          v-for="position in context.position_knowledge"
          :key="`${position.position_id}:${position.knowledge_base_id}`"
          :position="position"
        />
      </template>
      <el-alert v-else-if="context.position_knowledge?.length" title="岗位职责暂时无法显示，请刷新页面重试" type="warning" :closable="false" />
      <template v-else>
        <el-input
          model-value=""
          type="textarea"
          :rows="10"
          disabled
          aria-label="岗位职责正文"
          placeholder="配置岗位知识库后，可在此填写岗位职责并保存为《岗位职责.md》"
        />
        <p class="hint">暂无可用的岗位知识库，尚不能保存。请管理员先在用户管理中分配岗位，并核对岗位知识库绑定及知识读写权限。</p>
      </template>
      <el-button v-if="hasPerms('position:list') && router.hasRoute('SystemPosition')" link type="primary" @click="router.push({ name: 'SystemPosition' })">进入岗位管理</el-button>
      <h3>个人偏好</h3>
      <el-input
        v-model="instructions"
        type="textarea"
        :rows="5"
        maxlength="2000"
        show-word-limit
        placeholder="例如：用中文简洁回答；拟写家长通知时先给出可直接发送的正文。请勿填写姓名、联系方式等个人信息。"
      />
      <el-button
        data-action="primary"
        class="save-preferences"
        type="primary"
        :loading="saving"
        @click="savePersonal"
        >保存偏好</el-button
      >
      <h3>我的角色模板</h3>
      <p class="hint">
        使用管理员为本租户统一配置的模板，按你实际拥有的角色自动匹配，默认启用。可单独关闭或重新启用，仅影响本人的
        AI 工作指导，不改变角色、权限或实际任职。
      </p>
      <el-table
        v-if="context.available_templates.length"
        :data="context.available_templates"
      >
        <el-table-column prop="template_name" label="模板名称" />
        <el-table-column label="操作" width="80">
          <template #default="{ row }">
            <el-button link type="primary" @click="viewingTemplate = row as PersonalRoleTemplate">
              查看
            </el-button>
          </template>
        </el-table-column>
        <el-table-column label="本人是否启用" width="150">
          <template #default="{ row }">
            <el-switch
              :model-value="row.is_active"
              :loading="changingTemplate === row.id"
              :disabled="!!changingTemplate"
              :aria-label="`${row.template_name}：本人是否启用`"
              active-text="启用"
              inactive-text="关闭"
              @change="
                value =>
                  toggleTemplate(row as PersonalRoleTemplate, value === true)
              "
            />
          </template>
        </el-table-column>
      </el-table>
      <p v-else class="hint">
        当前租户暂无与你的角色匹配且已启用的模板，请联系管理员检查角色模板配置。
      </p>
      <el-collapse class="mt-4"
        ><el-collapse-item title="查看最终生效提示">
          <pre>{{ context.prompt }}</pre>
        </el-collapse-item></el-collapse
      >
    </template>
    <el-dialog
      append-to-body
      :model-value="!!viewingTemplate"
      :title="viewingTemplate?.template_name"
      width="min(640px, 94vw)"
      @close="viewingTemplate = undefined"
    >
      <p class="hint">管理员配置的模板原文；身份变量会在生成最终提示时自动替换。</p>
      <pre class="template-content">{{ viewingTemplate?.instructions }}</pre>
      <template #footer>
        <el-button @click="viewingTemplate = undefined">关闭</el-button>
      </template>
    </el-dialog>
  </section>
</template>

<style scoped>
.save-preferences {
  margin-top: 6px;
}

.ai-settings {
  max-width: 880px;
  padding-bottom: 32px;
}
h2 {
  font-size: 20px;
  margin-bottom: 16px;
}
h3 {
  font-size: 16px;
  margin: 24px 0 12px;
}
.hint {
  color: var(--el-text-color-secondary);
  line-height: 1.7;
  margin: 12px 0;
}
pre {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  line-height: 1.7;
}
.template-content {
  max-height: 60vh;
  overflow-y: auto;
}
ul {
  padding-left: 20px;
  line-height: 1.8;
}
</style>
