<script setup lang="ts">
import { computed } from "vue";
import type { MesScheduleResource } from "@plugins/mes/web/src/api/mes";
import { duration, today } from "./model";

const props = defineProps<{
  resources: MesScheduleResource[];
  days: string[];
  editable: boolean;
  loading: boolean;
}>();
const emit = defineEmits<{
  open: [resource: MesScheduleResource, day?: string];
  add: [resource: MesScheduleResource];
}>();

const status = {
  disabled: ["已停用", "neutral"],
  unassigned: ["待分配", "pending"],
  pending: ["待排", "pending"],
  scheduled: ["有计划", "scheduled"],
  outside: ["窗口内无计划", "neutral"],
  empty: ["暂无任务", "neutral"]
} as const;
function cardStatus(
  resource: MesScheduleResource,
  pending: number,
  hasPlan: boolean
) {
  if (!resource.is_active) return status.disabled;
  if (resource.kind === "unassigned") return status.unassigned;
  if (pending > 0) return status.pending;
  if (hasPlan) return status.scheduled;
  return resource.task_count ? status.outside : status.empty;
}
const cards = computed(() => {
  const currentDay = today();
  return props.resources.map(resource => {
    const pending = resource.task_count - resource.scheduled_count;
    const load = new Map(resource.daily_load.map(item => [item.day, item]));
    const [label, tone] = cardStatus(
      resource,
      pending,
      props.days.some(day => load.has(day))
    );
    const metadata = [
      resource.equipment_no,
      resource.kind === "station" ? "手工工作站" : "",
      resource.process_name || resource.work_center_name || "未限定工艺"
    ]
      .filter(Boolean)
      .join(" · ");
    const daily = props.days.map(day => {
      const plan = load.get(day);
      const isToday = day === currentDay;
      return {
        day,
        shortDay: day.endsWith("-01")
          ? day.slice(5).replace("-", "/")
          : day.slice(-2),
        hasPlan: !!plan,
        isToday,
        amount: plan ? compactDuration(plan.planned_minutes) : "—",
        title: `${resource.equipment_name} · ${day}${isToday ? "（今天）" : ""} · ${plan ? `${plan.task_count} 道工序 · ${duration(plan.planned_minutes)}` : "暂无计划"}`
      };
    });
    return { resource, pending, daily, label, tone, metadata };
  });
});
const columns = computed(() => Math.min(props.days.length, 8));

function compactDuration(minutes: number) {
  if (minutes > 0 && minutes < 1) return "<1分";
  const rounded = Math.round(minutes);
  return rounded < 1000 ? `${rounded}分` : `${Math.round(minutes / 60)}时`;
}
</script>

<template>
  <section
    v-loading="loading"
    class="equipment-board"
    aria-labelledby="equipment-board-title"
  >
    <header class="equipment-board-header">
      <h3 id="equipment-board-title">设备看板</h3>
      <div v-if="cards.length" class="equipment-legend">
        <span data-tone="pending">待排 / 待分配</span>
        <span data-tone="scheduled">有计划</span>
        <span data-tone="neutral">暂无任务</span>
      </div>
    </header>

    <el-empty
      v-if="!loading && !cards.length"
      description="当前范围暂无设备或任务"
    />
    <div v-else class="equipment-grid">
      <article
        v-for="{ resource, pending, daily, label, tone, metadata } in cards"
        :key="resource.resource_key"
        class="equipment-card"
        :data-tone="tone"
      >
        <header class="equipment-heading">
          <h4>{{ resource.equipment_name }}</h4>
          <span class="equipment-status">{{ label }}</span>
        </header>
        <p class="equipment-meta" :title="metadata">{{ metadata }}</p>

        <dl class="equipment-stats">
          <div>
            <dt>已安排</dt>
            <dd>{{ resource.scheduled_count }}</dd>
          </div>
          <div>
            <dt>待排</dt>
            <dd :class="{ 'pending-value': pending > 0 }">{{ pending }}</dd>
          </div>
          <div>
            <dt>计划时长合计</dt>
            <dd>{{ duration(resource.planned_minutes) }}</dd>
          </div>
        </dl>

        <div v-if="columns" class="equipment-days">
          <p>按日计划</p>
          <div class="equipment-day-grid" :style="{ '--day-columns': columns }">
            <button
              v-for="entry in daily"
              :key="entry.day"
              type="button"
              class="equipment-day"
              :class="{
                'has-plan': entry.hasPlan,
                'current-day': entry.isToday
              }"
              :title="entry.title"
              :aria-label="entry.title"
              @click="emit('open', resource, entry.day)"
            >
              <span class="day-amount">{{ entry.amount }}</span>
              <span class="day-label">{{ entry.shortDay }}</span>
            </button>
          </div>
        </div>

        <footer class="equipment-actions">
          <el-button type="primary" link @click="emit('open', resource)"
            >任务管理 / 计划</el-button
          >
          <el-button
            v-if="
              editable && resource.kind === 'equipment' && resource.is_active
            "
            link
            @click="emit('add', resource)"
            >添加待排任务</el-button
          >
        </footer>
      </article>
    </div>
  </section>
</template>

<style scoped>
.equipment-board {
  --board-blue: #245bdd;
  --board-blue-text: #245bdd;
  --board-amber: #a66308;
  --board-amber-text: #8a5004;
  --board-slate: #8a9bb2;
  --board-ink: #152540;
  --board-muted: #536781;

  min-width: 0;
  color: var(--board-ink);
}

:global(html.dark) .equipment-board {
  --board-blue: #3165de;
  --board-blue-text: #91b5ff;
  --board-amber-text: #f5c076;
  --board-ink: #e4edf9;
  --board-muted: #a8b5c7;
}

.equipment-board-header,
.equipment-legend,
.equipment-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 16px;
  align-items: center;
}

.equipment-board-header {
  justify-content: space-between;
  margin-bottom: 18px;
}

.equipment-board-header h3 {
  margin: 0;
  font-size: 24px;
  line-height: 1.35;
}

.equipment-legend {
  font-size: 12px;
  color: var(--board-muted);
}

.equipment-legend span::before {
  display: inline-block;
  width: 8px;
  height: 8px;
  margin-right: 6px;
  vertical-align: 1px;
  content: "";
  background: var(--status-color);
  border-radius: 50%;
}

[data-tone="pending"] {
  --status-color: var(--board-amber);
}
[data-tone="scheduled"] {
  --status-color: var(--board-blue);
}
[data-tone="neutral"] {
  --status-color: var(--board-slate);
}

.equipment-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(100%, 300px), 1fr));
  gap: 16px;
}

.equipment-card {
  display: flex;
  min-width: 0;
  flex-direction: column;
  padding: 16px 16px 12px;
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-light);
  border-inline-start: 3px solid var(--status-color);
  border-radius: 10px;
  box-shadow: 0 1px 2px rgb(15 35 65 / 7%);
}

.equipment-heading {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  justify-content: space-between;
}

.equipment-heading h4 {
  min-width: 0;
  margin: 0;
  overflow-wrap: anywhere;
  font-size: 17px;
  font-weight: 700;
  line-height: 1.5;
}

.equipment-status {
  flex-shrink: 0;
  padding: 2px 8px;
  color: white;
  font-size: 12px;
  font-weight: 600;
  line-height: 18px;
  background: var(--status-color);
  border-radius: 6px;
}

[data-tone="neutral"] .equipment-status {
  color: var(--board-muted);
  background: var(--el-fill-color);
}

.equipment-meta {
  margin: 3px 0 14px;
  overflow: hidden;
  font-size: 12px;
  line-height: 19px;
  color: var(--board-muted);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.equipment-stats {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) minmax(6em, auto);
  gap: 8px;
  margin: 0 0 13px;
}

.equipment-stats dt,
.equipment-days p {
  font-size: 12px;
  color: var(--board-muted);
}

.equipment-stats dd {
  margin: 2px 0 0;
  font-size: 17px;
  font-weight: 650;
  font-variant-numeric: tabular-nums;
  overflow-wrap: anywhere;
  line-height: 1.4;
}

.equipment-stats .pending-value {
  color: var(--board-amber-text);
}

.equipment-days p {
  margin: 0 0 6px;
  font-weight: 600;
}

.equipment-days {
  container-type: inline-size;
}

.equipment-day-grid {
  display: grid;
  grid-template-columns: repeat(var(--day-columns), minmax(0, 1fr));
  gap: 5px 3px;
}

@container (max-width: 248px) {
  .equipment-day-grid {
    grid-template-columns: repeat(min(var(--day-columns), 4), minmax(0, 1fr));
  }
}

.equipment-day {
  display: grid;
  min-width: 0;
  gap: 2px;
  padding: 0;
  color: var(--board-muted);
  font-variant-numeric: tabular-nums;
  text-align: center;
  cursor: pointer;
  background: transparent;
  border: 0;
  border-radius: 5px;
}

.day-amount {
  display: block;
  min-width: 0;
  min-height: 24px;
  overflow: hidden;
  font-size: 10px;
  font-weight: 600;
  line-height: 22px;
  text-overflow: ellipsis;
  white-space: nowrap;
  background: var(--el-fill-color-light);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 5px;
}

.day-label {
  font-size: 11px;
  line-height: 16px;
}

.has-plan .day-amount {
  color: white;
  background: var(--board-blue);
  border-color: var(--board-blue);
}

.current-day .day-label {
  color: var(--board-blue-text);
  font-weight: 700;
}

.equipment-day:hover .day-amount,
.equipment-day:focus-visible .day-amount {
  border-color: var(--board-blue-text);
}

.equipment-day:focus-visible {
  outline: 2px solid var(--board-blue-text);
  outline-offset: 2px;
}

.equipment-actions {
  margin-top: auto;
  padding-top: 12px;
}

.equipment-actions .el-button {
  min-height: 28px;
  margin-left: 0;
  font-size: 13px;
}

.equipment-actions .el-button--primary {
  color: var(--board-blue-text);
}
</style>
