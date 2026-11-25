<script setup lang="ts">
import { computed, ref } from "vue";
import pluginApplications from "virtual:plugin-applications";
import { useRouter } from "vue-router";
import { transformI18n } from "@/plugins/i18n";
import { usePermissionStoreHook } from "@/store/modules/permission";
import PersonalWorkbench from "@/views/workbench/index.vue";
import { resolveModuleDestination, sidebarModuleLabel } from "./moduleRoutes";

defineOptions({ name: "ApplicationWorkbench" });

type ModuleCard = {
  title: string;
  summary: string;
  icon: string;
  path: string;
  rootPath: string;
  tone: "blue" | "cyan" | "violet" | "green" | "orange" | "rose";
};

const router = useRouter();
const permissionStore = usePermissionStoreHook();
const assistantOpen = ref(false);
const applicationsVisible = ref(false);

const moduleCards: ModuleCard[] = [
  ...pluginApplications,
  {
    title: "系统管理",
    summary: "用户、组织、权限与系统配置",
    icon: "ri:settings-3-line",
    path: "/system/user/index",
    rootPath: "/system",
    tone: "blue"
  }
];

const visibleModuleCards = computed<ModuleCard[]>(() =>
  permissionStore.sidebarMenus.flatMap((menu): ModuleCard[] => {
    const config = moduleCards.find(item => item.rootPath === menu.path);
    const destination = resolveModuleDestination(menu, config?.path);
    if (!destination || !menu.path) return [];
    const label = sidebarModuleLabel(menu);
    const title = label.meta?.title
      ? transformI18n(label.meta.title)
      : config?.title;
    if (!title) return [];
    const icon = label.meta?.icon;
    const summary =
      config?.summary?.trim() ||
      (menu.children ?? [])
        .flatMap(child => {
          if (
            child.meta?.showLink === false ||
            !resolveModuleDestination(child)
          )
            return [];
          const title = sidebarModuleLabel(child).meta?.title;
          return title ? [transformI18n(title)] : [];
        })
        .join("、");
    return [
      {
        rootPath: menu.path,
        title,
        icon:
          config?.icon ?? (typeof icon === "string" ? icon : "ri:apps-2-line"),
        summary,
        tone: config?.tone ?? "blue",
        path: destination
      }
    ];
  })
);

const commonModuleCards = computed(() =>
  moduleCards
    .flatMap(config =>
      visibleModuleCards.value.filter(item => item.rootPath === config.rootPath)
    )
    .slice(0, 6)
);

function openModule(item: ModuleCard) {
  const current = visibleModuleCards.value.find(
    card => card.rootPath === item.rootPath
  );
  if (!current) return;
  if (/^https?:\/\//i.test(current.path)) {
    window.open(current.path, "_blank", "noopener");
  } else {
    void router.push(current.path);
  }
}
</script>

<template>
  <main class="application-home">
    <section
      :class="['application-shell', { 'assistant-open': assistantOpen }]"
    >
      <PersonalWorkbench @assistant-state-change="assistantOpen = $event">
        <template #common-business>
          <header class="common-business-heading">
            <h2><IconifyIconOnline icon="ri:box-3-line" />常用业务</h2>
            <button type="button" @click="applicationsVisible = true">
              全部应用<IconifyIconOnline icon="ri:arrow-right-s-line" />
            </button>
          </header>
          <div class="common-business-grid" aria-label="常用业务">
            <button
              v-for="item in commonModuleCards"
              :key="item.rootPath"
              type="button"
              @click="openModule(item)"
            >
              <IconifyIconOnline :icon="item.icon" />
              <strong>{{ item.title }}</strong
              ><small v-if="item.summary" :title="item.summary">{{
                item.summary
              }}</small>
            </button>
          </div>
          <el-empty
            v-if="!commonModuleCards.length"
            :image-size="60"
            description="暂无获权的业务应用"
          />
        </template>
      </PersonalWorkbench>
      <el-dialog
        v-model="applicationsVisible"
        title="全部应用"
        width="min(1100px, 92vw)"
        append-to-body
      >
        <div class="module-grid" aria-label="业务模块">
          <button
            v-for="item in visibleModuleCards"
            :key="item.rootPath"
            :class="['module-card', `module-${item.tone}`]"
            type="button"
            @click="
              openModule(item);
              applicationsVisible = false;
            "
          >
            <span class="module-icon">
              <IconifyIconOnline :icon="item.icon" />
            </span>
            <span class="module-copy">
              <strong>{{ item.title }}</strong>
              <small v-if="item.summary" :title="item.summary">{{
                item.summary
              }}</small>
            </span>
            <span class="module-arrow">
              <IconifyIconOnline icon="ri:arrow-right-line" />
            </span>
          </button>
        </div>
        <el-empty
          v-if="!visibleModuleCards.length"
          description="暂无获权的业务应用"
        />
      </el-dialog>
    </section>
  </main>
</template>

<style scoped lang="scss">
.application-home {
  --navy: #173b68;
  --blue: #2f73bd;
  --workbench-background: #f5f9fe;

  min-height: 100%;
  color: #193655;
  background: var(--workbench-background);
}

.application-shell {
  width: min(1760px, calc(100% - 64px));
  padding: clamp(24px, 4vh, 42px) 0 36px;
  margin: 0 auto;
}

.application-shell.assistant-open {
  width: calc(100% - 12px);
  padding: 6px 0;
}

.common-business-heading {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
  min-height: 50px;
  padding-bottom: 14px;
  border-bottom: 1px solid #edf1f8;
}

.common-business-heading h2 {
  display: flex;
  gap: 10px;
  align-items: center;
  margin: 0;
  font-size: 21px;
  color: #100a43;
}

.common-business-heading h2 > svg {
  font-size: 27px;
  color: var(--el-color-primary);
}

.common-business-heading button {
  display: inline-flex;
  gap: 4px;
  align-items: center;
  padding: 0;
  font-family: inherit;
  font-size: 12px;
  color: var(--app-button-primary-ink);
  cursor: pointer;
  background: transparent;
  border: 0;
}

.common-business-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 6px;
  margin-top: 10px;
}

.common-business-grid button {
  display: grid;
  gap: 6px;
  justify-items: center;
  min-width: 0;
  min-height: 125px;
  padding: 12px 8px;
  font-family: inherit;
  text-align: center;
  cursor: pointer;
  background: var(--app-button-primary-soft);
  border: 1px solid transparent;
  border-radius: 7px;
}

.common-business-grid button:hover {
  background: var(--app-button-primary-hover-soft);
  border-color: var(--app-button-primary-border);
}

.common-business-grid button > svg {
  font-size: 32px;
  color: var(--el-color-primary);
}

.common-business-grid strong {
  font-size: 17px;
  color: #100a43;
}

.common-business-grid small {
  font-size: 12px;
  line-height: 1.5;
  color: #7c83a3;
}

.common-business-heading button:focus-visible,
.common-business-grid button:focus-visible {
  outline: 2px solid var(--el-color-primary);
  outline-offset: 3px;
}

.module-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
}

.module-card {
  --module-color: var(--el-color-primary);
  --module-soft: var(--el-color-primary-light-9);

  position: relative;
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  gap: 15px;
  align-items: center;
  min-width: 0;
  min-height: 132px;
  padding: 20px;
  overflow: hidden;
  font: inherit;
  text-align: left;
  cursor: pointer;
  background: #fff;
  border: 1px solid #dfe7f0;
  border-radius: 14px;
  box-shadow: 0 5px 18px rgb(34 75 117 / 4%);
  transition:
    transform 0.2s ease,
    border-color 0.2s ease,
    box-shadow 0.2s ease;
}

.module-card:hover,
.module-card:focus-visible {
  border-color: color-mix(in srgb, var(--module-color) 38%, #e3eaf2);
  box-shadow: 0 14px 29px rgb(29 77 129 / 12%);
  transform: translateY(-3px);
}

.module-icon {
  display: grid;
  place-items: center;
  width: 50px;
  height: 50px;
  font-size: 24px;
  color: var(--module-color);
  background: var(--module-soft);
  border-radius: 13px;
}

.module-copy {
  display: grid;
  gap: 5px;
  min-width: 0;
}

.module-copy strong {
  font-size: 17px;
  color: #213f5d;
}

.module-copy small {
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 12px;
  color: #7c8da2;
  white-space: nowrap;
}

.module-arrow {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  color: var(--module-color);
  background: var(--module-soft);
  border: 1px solid var(--el-color-primary-light-8);
  border-radius: 50%;
  transition: all 0.2s ease;
}

.module-card:hover .module-arrow {
  color: #fff;
  background: var(--module-color);
  border-color: var(--module-color);
  transform: translateX(2px);
}

@media (width <= 900px) {
  .module-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (width <= 620px) {
  .application-shell {
    width: calc(100% - 28px);
    padding-top: 20px;
  }

  .module-grid {
    grid-template-columns: 1fr;
    gap: 12px;
  }

  .module-card {
    min-height: 118px;
    padding: 18px;
  }
}
</style>
