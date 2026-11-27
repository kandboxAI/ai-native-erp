<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { useSampleApi } from "@plugins/sample_app/web/src/api/sample_app";
const { getPluginStatus } = useSampleApi();

const router = useRouter();
const loading = ref(false);
const connected = ref(false);
const status = ref("正在检查业务连接…");
const groups = [
  {
    title: "薪酬管理",
    text: "从员工档案到每月发薪",
    entries: [
      {
        title: "员工档案",
        text: "维护发薪员工、入职信息与脱敏收款账号。",
        path: "/sample-app/employee",
        mark: "员",
      },
      {
        title: "月度考勤",
        text: "登记出勤与加班，支持导入考勤表格。",
        path: "/sample-app/attendance",
        mark: "勤",
      },
      {
        title: "员工定薪",
        text: "维护基本工资与绩效，调薪不改变缴费基数。",
        path: "/sample-app/salary",
        mark: "薪",
      },
      {
        title: "缴费基数",
        text: "独立维护社保与公积金基数，保留年度调整历史。",
        path: "/sample-app/social-bases",
        mark: "保",
      },
      {
        title: "工资核算",
        text: "计算应发、个税与实发工资，确认后封账。",
        path: "/sample-app/payroll",
        mark: "算",
      },
    ],
  },
  {
    title: "经营与资金",
    text: "管理项目回款与日常收支",
    entries: [
      {
        title: "项目台账",
        text: "跟进合同、回款计划与实际收款，归集项目成本。",
        path: "/sample-app/project",
        mark: "项",
      },
      {
        title: "资金管理",
        text: "管理账户流水、员工借还款、报销与固定成本。",
        path: "/sample-app/cash",
        mark: "资",
      },
      {
        title: "社保与工资支付",
        text: "核对月度缴费，关联实际流水，跟踪个人扣回与当月成本。",
        path: "/sample-app/funds/social",
        mark: "付",
      },
      {
        title: "计薪参数",
        text: "设置日薪口径、加班倍率、个税与社保方案。",
        path: "/sample-app/setting",
        mark: "设",
      },
    ],
  },
];
async function checkConnection() {
  if (loading.value) return;
  loading.value = true;
  connected.value = false;
  status.value = "正在检查业务连接…";
  try {
    const response = await getPluginStatus();
    connected.value = response.code === 0 && response.data?.status === "ready";
    status.value = connected.value
      ? "业务已就绪，数据按账号授权范围展示"
      : response.message || "业务暂不可用，请确认插件已启用及组织配置有效。";
  } catch {
    status.value =
      "业务连接失败，请确认快盒已启用、组织配置有效，并重新登录后重试。";
  } finally {
    loading.value = false;
  }
}
onMounted(checkConnection);
</script>

<template>
  <section class="sample-workbench">
    <header class="workbench-header">
      <div class="brand">
        <span class="brand-mark" aria-hidden="true">快</span>
        <div>
          <p class="eyebrow">快盒 · 业务工作台</p>
          <h1>让日常经营，井然有序</h1>
          <p class="intro">员工、薪酬、项目与资金，在这里开始处理。</p>
        </div>
      </div>
      <el-button type="primary" @click="router.push('/sample-app/payroll')"
        >进入工资核算 →</el-button
      >
    </header>
    <div
      class="connection"
      :class="{ 'connection-error': !loading && !connected }"
      role="status"
      aria-live="polite"
    >
      <span
        class="status-dot"
        :class="{ ready: connected }"
        aria-hidden="true"
      /><span>{{ status }}</span>
      <el-button
        v-if="!loading && !connected"
        link
        type="primary"
        @click="checkConnection"
        >重新检查</el-button
      >
    </div>
    <section
      v-for="(group, index) in groups"
      :key="group.title"
      class="entry-group"
      :aria-labelledby="`group-${index}`"
    >
      <div class="group-heading">
        <h2 :id="`group-${index}`">{{ group.title }}</h2>
        <p>{{ group.text }}</p>
      </div>
      <div class="entry-grid">
        <button
          v-for="item in group.entries"
          :key="item.path"
          class="entry-card"
          type="button"
          @click="router.push(item.path)"
        >
          <span
            class="entry-mark"
            :class="{ green: index === 1 }"
            aria-hidden="true"
            >{{ item.mark }}</span
          >
          <span class="entry-body"
            ><strong>{{ item.title }}</strong
            ><span class="entry-description">{{ item.text }}</span></span
          ><span class="entry-arrow" aria-hidden="true">↗</span>
        </button>
      </div>
    </section>
    <footer class="workbench-note">
      <strong>首次使用</strong
      ><span
        >先维护员工与计薪参数，再登记考勤、定薪并核算工资。组织与部门在系统管理中维护。</span
      >
    </footer>
  </section>
</template>

<style scoped>
.sample-workbench {
  padding: 28px;
  color: var(--el-text-color-primary);
}
.workbench-header {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  padding: 30px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 16px;
  background: linear-gradient(
    120deg,
    var(--el-color-primary-light-9),
    var(--el-bg-color)
  );
}
.brand {
  display: flex;
  align-items: center;
  gap: 20px;
  min-width: 0;
}
.brand-mark {
  display: grid;
  flex-shrink: 0;
  place-items: center;
  width: 58px;
  height: 58px;
  border-radius: 16px;
  background: var(--el-color-primary);
  color: var(--el-color-white);
  font-size: 26px;
  font-weight: 700;
}
.eyebrow {
  margin: 0 0 8px;
  color: var(--el-color-primary);
  font-size: 13px;
  font-weight: 600;
}
h1 {
  margin: 0;
  font-size: clamp(22px, 2vw, 28px);
  font-weight: 650;
  line-height: 1.4;
}
.intro {
  margin: 10px 0 0;
  color: var(--el-text-color-secondary);
  font-size: 14px;
  line-height: 1.7;
}
.connection {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 9px;
  margin: 16px 0 30px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
  line-height: 1.6;
}
.connection-error {
  color: var(--el-color-warning-dark-2);
}
.status-dot {
  width: 7px;
  height: 7px;
  flex-shrink: 0;
  border-radius: 50%;
  background: var(--el-color-warning);
}
.status-dot.ready {
  background: var(--el-color-success);
}
.entry-group + .entry-group {
  margin-top: 30px;
}
.group-heading {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 14px;
}
h2 {
  margin: 0;
  font-size: 17px;
  font-weight: 600;
}
.group-heading p {
  margin: 0;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
.entry-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
}
.entry-card {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  min-width: 0;
  padding: 24px 20px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 12px;
  background: var(--el-bg-color);
  color: inherit;
  text-align: left;
  font: inherit;
  cursor: pointer;
  transition:
    border-color 0.18s,
    box-shadow 0.18s;
}
.entry-card:hover {
  border-color: var(--el-color-primary-light-5);
  box-shadow: var(--el-box-shadow-light);
}
.entry-card:focus-visible {
  outline: 2px solid var(--el-color-primary);
  outline-offset: 3px;
}
.entry-mark {
  display: grid;
  flex-shrink: 0;
  place-items: center;
  width: 40px;
  height: 40px;
  border-radius: 10px;
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
  font-size: 17px;
  font-weight: 600;
}
.entry-mark.green {
  background: var(--el-color-success-light-9);
  color: var(--el-color-success);
}
.entry-body {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 9px;
  min-width: 0;
}
.entry-body strong {
  font-size: 15px;
  font-weight: 600;
}
.entry-description {
  color: var(--el-text-color-secondary);
  font-size: 13px;
  line-height: 1.8;
  overflow-wrap: anywhere;
}
.entry-arrow {
  color: var(--el-text-color-placeholder);
}
.workbench-note {
  display: flex;
  align-items: baseline;
  gap: 14px;
  margin-top: 30px;
  padding: 18px 20px;
  border-radius: 10px;
  background: var(--el-fill-color-light);
  color: var(--el-text-color-secondary);
  font-size: 13px;
  line-height: 1.8;
}
.workbench-note strong {
  flex-shrink: 0;
  color: var(--el-text-color-regular);
}
@media (min-width: 1500px) {
  .entry-grid {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }
}
@media (max-width: 1100px) {
  .entry-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
@media (max-width: 640px) {
  .sample-workbench {
    padding: 16px;
  }
  .workbench-header {
    padding: 20px;
  }
  .brand {
    align-items: flex-start;
    gap: 12px;
  }
  .brand-mark {
    width: 42px;
    height: 42px;
    font-size: 20px;
    border-radius: 12px;
  }
  .entry-grid {
    grid-template-columns: minmax(0, 1fr);
  }
  .entry-card {
    padding: 20px;
  }
  .workbench-note {
    flex-direction: column;
    gap: 4px;
  }
}
</style>
