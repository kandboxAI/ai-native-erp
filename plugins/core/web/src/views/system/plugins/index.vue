<template>
  <ReListPresentation>
  <div
    v-loading="loading"
    class="sys-module sys-page application-management list-page list-presentation-container"
  >
    <ReListHeading />
    <section
      class="list-section"
      v-if="suites.length"
      v-loading="busyKey.startsWith('suite:')"
    >
      <ReListTable
        list-key="index-0"
        list-local
        :list-refresh="load"
        :data="suites"
        row-key="suite_key"
      >
        <el-table-column prop="name" label="套件" min-width="140" />
        <el-table-column label="状态" min-width="130">
          <template #default="{ row }">
            {{ suiteStatusLabel(row as SuiteState) }}
          </template>
        </el-table-column>
        <el-table-column prop="components" label="包含插件" min-width="220">
          <template #default="{ row }">{{
            row.components.map(item => item.name).join("、")
          }}</template>
        </el-table-column>
        <el-table-column label="操作" min-width="220">
          <template #default="{ row }">
            <el-button
              data-action="success"
              v-if="!row.is_active"
              type="primary"
              link
              :disabled="!!busyKey"
              @click="runSuite(row as SuiteState, 'enable')"
              >启用整套</el-button
            >
            <el-button
              data-action="primary"
              v-if="row.upgrade_available"
              type="primary"
              link
              :disabled="!!busyKey"
              @click="runSuite(row as SuiteState, 'upgrade')"
              >升级整套</el-button
            >
            <el-button
              data-action="warning"
              v-if="row.components.some(item => item.is_active)"
              type="danger"
              link
              :disabled="!!busyKey"
              @click="runSuite(row as SuiteState, 'disable')"
              >停用套件</el-button
            >
          </template>
        </el-table-column>

        <template #list-title>业务套件</template>
      </ReListTable>
      <el-button
        data-action="neutral"
        link
        type="primary"
        class="component-toggle"
        @click="showComponents = !showComponents"
      >
        {{ showComponents ? "收起插件明细" : "查看插件明细与单独管理" }}
      </el-button>
    </section>
    <section
      class="list-section"
      v-if="visiblePlugins.length || (!loading && !suites.length)"
    >
      <ReListTable
        list-key="index-1"
        list-local
        :list-refresh="load"
        :data="visiblePlugins"
        row-key="plugin_key"
        empty-text="暂无可管理的业务插件"
      >
        <el-table-column prop="name" label="插件" min-width="150" />
        <el-table-column prop="plugin_key" label="标识" min-width="100" />
        <el-table-column prop="version" label="部署版本" min-width="110" />
        <el-table-column
          prop="installed_version"
          label="已安装版本"
          min-width="110"
        >
          <template #default="{ row }">{{
            row.installed_version || "—"
          }}</template>
        </el-table-column>
        <el-table-column prop="requires" label="依赖" min-width="150">
          <template #default="{ row }">{{
            row.requires.join("、") || "无"
          }}</template>
        </el-table-column>
        <el-table-column
          prop="provisioning_status_code"
          label="安装状态"
          min-width="110"
        >
          <template #default="{ row }">
            <span :title="row.last_error_type || ''">{{
              statusLabel[row.provisioning_status_code]
            }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="is_active" label="租户状态" min-width="100">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'info'">{{
              row.is_active ? "启用" : "停用"
            }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="240" fixed="right">
          <template #default="{ row }">
            <el-button
              data-action="primary"
              v-if="row.upgrade_available"
              link
              type="primary"
              :loading="busyKey === row.plugin_key && busyAction === 'upgrade'"
              :disabled="!!busyKey"
              @click="runUpgrade(row as PluginState)"
              >升级到 {{ row.version }}</el-button
            >
            <el-button
              :data-action="row.is_active ? 'warning' : ['failed', 'installing'].includes(row.provisioning_status_code) ? 'primary' : 'success'"
              link
              type="primary"
              :loading="busyKey === row.plugin_key && busyAction === 'state'"
              :disabled="!!busyKey"
              @click="changeState(row as PluginState)"
              >{{
                row.is_active
                  ? "停用"
                  : row.provisioning_status_code === "failed"
                    ? "重试开通"
                    : row.provisioning_status_code === "installing"
                      ? "继续开通"
                      : "启用"
              }}</el-button
            >
          </template>
        </el-table-column>

        <template #list-title>{{
          showComponents ? "插件明细" : "独立插件"
        }}</template>
      </ReListTable>
    </section>
  </div>

  </ReListPresentation>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  listPlugins,
  setPluginActive,
  upgradePlugin,
  listSuites,
  changeSuite,
  type PluginState,
  type SuiteState
} from "@/api/plugins";
import { getHttpErrorMessage } from "@/utils/http";
import { clearAsyncRoutesCache } from "@/utils/auth";

defineOptions({ name: "PluginManagement" });

const plugins = ref<PluginState[]>([]);
const suites = ref<SuiteState[]>([]);
const showComponents = ref(false);
const visiblePlugins = computed(() => {
  const bundled = new Set(suites.value.flatMap(suite => suite.plugins));
  return showComponents.value
    ? plugins.value
    : plugins.value.filter(item => !bundled.has(item.plugin_key));
});
const loading = ref(false);
const busyKey = ref("");
const busyAction = ref<"state" | "upgrade" | "">("");
const statusLabel: Record<PluginState["provisioning_status_code"], string> = {
  pending: "待开通",
  installing: "开通中",
  ready: "已就绪",
  failed: "开通失败"
};

function suiteStatusLabel(row: SuiteState) {
  if (row.provisioning_status_code === "failed") return "开通失败";
  if (row.provisioning_status_code === "installing") return "开通中";
  if (row.is_active) return "已启用";
  if (row.components.some(item => item.is_active)) return "部分启用";
  return row.components.every(item => item.installed_version)
    ? "未启用"
    : "待开通";
}

async function load() {
  loading.value = true;
  try {
    const [pluginResponse, suiteResponse] = await Promise.all([
      listPlugins(),
      listSuites()
    ]);
    plugins.value = pluginResponse.data;
    suites.value = suiteResponse.data;
  } catch (error) {
    ElMessage.error(getHttpErrorMessage(error, "读取应用列表失败"));
  } finally {
    loading.value = false;
  }
}

async function runSuite(
  row: SuiteState,
  action: "enable" | "disable" | "upgrade"
) {
  const detail =
    action === "enable"
      ? "将同时启用所需插件。首次启用会创建所需数据表并初始化配置。"
      : action === "upgrade"
        ? "将更新有新版本的插件，并保留各插件当前的启停状态。"
        : "停用后保留数据，其他已启用业务仍需要的共享插件会保留。";
  const actionLabel = { enable: "启用", disable: "停用", upgrade: "升级" }[
    action
  ];
  try {
    await ElMessageBox.confirm(
      `确认${actionLabel}当前租户的“${row.name}”？${detail}`,
      `${actionLabel}业务套件`,
      {
        confirmButtonClass:
          action === "disable"
            ? "app-button-warning"
            : action === "enable"
              ? "app-button-success"
              : "",
        type: "warning",
        confirmButtonText: "确认",
        cancelButtonText: "取消"
      }
    );
  } catch {
    return;
  }
  busyKey.value = `suite:${row.suite_key}`;
  try {
    const result = (await changeSuite(row.suite_key, action)).data;
    const retained = result.retained_plugins
      .map(item => item.plugin_key)
      .join("、");
    ElMessage.success(
      retained
        ? `操作完成，保留共享插件：${retained}`
        : "套件操作完成，正在刷新权限与菜单"
    );
    clearAsyncRoutesCache();
    window.location.reload();
  } catch (error) {
    ElMessage.error(getHttpErrorMessage(error, "套件操作失败"));
    // Earlier components may already be ready even when a later component failed.
    clearAsyncRoutesCache();
  } finally {
    busyKey.value = "";
    await load();
  }
}

async function changeState(row: PluginState) {
  const active = !row.is_active;
  try {
    await ElMessageBox.confirm(
      active
        ? `确认给当前租户启用“${row.name}”？首次启用会创建所需数据表并初始化配置。`
        : `确认给当前租户停用“${row.name}”？业务数据会保留。`,
      "确认操作",
      {
        confirmButtonClass: active ? "app-button-success" : "app-button-warning",
        type: "warning",
        confirmButtonText: "确认",
        cancelButtonText: "取消"
      }
    );
  } catch {
    return;
  }
  busyKey.value = row.plugin_key;
  busyAction.value = "state";
  try {
    await setPluginActive(row.plugin_key, active);
    ElMessage.success(
      active ? "已启用，正在刷新权限与菜单" : "已停用，正在刷新权限与菜单"
    );
    clearAsyncRoutesCache();
    window.location.reload();
  } catch (error) {
    ElMessage.error(getHttpErrorMessage(error, "操作失败"));
  } finally {
    busyKey.value = "";
    busyAction.value = "";
    await load();
  }
}

async function runUpgrade(row: PluginState) {
  try {
    await ElMessageBox.confirm(
      `确认将当前租户的“${row.name}”从 ${row.installed_version} 升级到 ${row.version}？升级期间该插件及依赖它的功能暂不可用。成功后保持当前${row.is_active ? "启用" : "停用"}状态。`,
      "升级插件",
      {
        type: "warning",
        confirmButtonText: "确认升级",
        cancelButtonText: "取消"
      }
    );
  } catch {
    return;
  }
  busyKey.value = row.plugin_key;
  busyAction.value = "upgrade";
  try {
    const result = (await upgradePlugin(row.plugin_key)).data;
    ElMessage.success(
      `已升级到 ${result.installed_version}，${result.is_active ? "保持启用" : "保持停用"}，正在刷新权限与菜单`
    );
    clearAsyncRoutesCache();
    window.location.reload();
  } catch (error) {
    ElMessage.error(getHttpErrorMessage(error, "升级失败"));
  } finally {
    busyKey.value = "";
    busyAction.value = "";
    await load();
  }
}

onMounted(load);
</script>

<style scoped lang="scss">
@use "../system-styles.scss";

.application-management {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.application-header h1 {
  margin: 0;
  font-size: 24px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.application-header p {
  margin: 8px 0 0;
  font-size: 14px;
  color: var(--el-text-color-secondary);
}

.section-title {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.page-tip {
  font-size: 14px;
  color: var(--el-text-color-secondary);
}

.component-toggle {
  margin-top: 12px;
}
</style>
