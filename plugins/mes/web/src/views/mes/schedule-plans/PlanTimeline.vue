<script setup lang="ts">
import { computed, ref, watch } from "vue";
import type {
  PlanDetail,
  PlanSegment,
} from "@plugins/mes/web/src/api/mesSchedulePlans";
import {
  equipmentLabel,
  hour,
  personLabel,
  rangeHours,
  stageLabels,
  timelineLanes,
  timelineStages,
  timelineWindow,
  type TimelineRange,
  type TimelineView,
} from "./timeline";

const props = defineProps<{
  startAt: string;
  endAt: string;
  segments: PlanSegment[];
  operations: PlanDetail["operations"];
  completions: PlanDetail["result"]["completions"];
  search: string;
}>();

const view = ref<TimelineView>("order");
const range = ref<TimelineRange>("work");
const anchor = ref<number>();
const selection = ref<{ title: string; details: string[]; at?: number }>();
const dialogVisible = ref(false);
const viewNames: Record<TimelineView, string> = {
  order: "工单",
  equipment: "设备",
  person: "人员",
};
const bounds = computed(() => ({
  start: Date.parse(props.startAt),
  end: Date.parse(props.endAt),
}));
const stages = computed(() => timelineStages(props.segments));
const window = computed(() =>
  timelineWindow(
    bounds.value,
    range.value,
    stages.value[0]?.start ?? bounds.value.start,
    anchor.value,
  ),
);
const lanes = computed(() =>
  timelineLanes(
    stages.value,
    props.operations,
    props.completions,
    window.value,
    view.value,
    range.value,
  ),
);
const canGoBack = computed(() => window.value.start > bounds.value.start);
const canGoForward = computed(() => window.value.end < bounds.value.end);
const dateTime = new Intl.DateTimeFormat("zh-CN", {
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});
const shortTime = new Intl.DateTimeFormat("zh-CN", {
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});
const shortDate = new Intl.DateTimeFormat("zh-CN", {
  month: "2-digit",
  day: "2-digit",
});
const format = (value: number) => dateTime.format(value);
const position = (time: number) => {
  const { start, end } = window.value;
  return Math.max(0, Math.min(100, ((time - start) / (end - start)) * 100));
};
const ticks = computed(() => {
  const { start, end } = window.value;
  const duration = (end - start) / hour;
  const step =
    [0.25, 0.5, 1, 2, 4, 8, 12, 24, 48, 96, 168].find(
      (value) => duration <= value * 8,
    ) ?? 168;
  const formatter = step >= 24 ? shortDate : shortTime;
  return Array.from({ length: Math.ceil(duration / step) }, (_, i) => {
    const time = start + i * step * hour;
    return { time, left: position(time), label: formatter.format(time) };
  }).filter((tick) => tick.left <= (step >= 24 ? 94 : 87.5));
});

type Lane = (typeof lanes.value)[number];
type Bar = Lane["tracks"][number][number];
type Event = Lane["milestones"][number];

function move(direction: -1 | 1) {
  const { start, end } = window.value;
  anchor.value = start + direction * (end - start);
}

function setRange(value: TimelineRange) {
  if (value !== "overview" && range.value !== "overview")
    anchor.value = window.value.start;
  range.value = value;
}

watch(
  () => props.search,
  () => {
    anchor.value = undefined;
  },
);

function stageName(bar: Bar) {
  const { segment } = bar.stage;
  if (segment.is_independent_inspection) return "独立检验";
  return range.value !== "detail" && bar.kind === "run"
    ? "机加工"
    : (stageLabels[bar.kind] ?? bar.kind);
}
function barLabel(bar: Bar) {
  const { segment } = bar.stage;
  return view.value === "order" && stageName(bar) === "机加工"
    ? segment.operation_name
    : view.value === "order"
      ? `${segment.operation_name} · ${stageName(bar)}`
      : `${segment.work_order_no} · ${segment.operation_name}`;
}
function barDetails(bar: Bar) {
  const { segment } = bar.stage;
  return [
    `${segment.production_phase_code === "first" ? "首件" : "剩余批量"} · ${stageName(bar)}${bar.count > 1 ? `（${bar.count} 个连续阶段）` : ""}`,
    `${format(bar.start)} — ${format(bar.end)}`,
    segment.equipment_id
      ? `设备 ${equipmentLabel(segment)}`
      : "",
    segment.person_capacity_units_snapshot
      ? `人员 ${personLabel(segment)} · ${segment.person_capacity_units_snapshot === 1 ? "两机照看" : "专注操作"}`
      : "",
  ].filter(Boolean);
}
function showBar(bar: Bar) {
  const { segment } = bar.stage;
  selection.value = {
    title: `${segment.work_order_no} / ${segment.operation_name}`,
    details: barDetails(bar),
    at: Math.max(bar.start, window.value.start),
  };
  dialogVisible.value = true;
}

function eventText(event: Event) {
  const { start, end } = bounds.value;
  const outside =
    event.at < start
      ? "（方案窗口前）"
      : event.at > end
        ? "（方案窗口后）"
        : "";
  return `${event.label} ${format(event.at)}${outside}`;
}
function eventMarkers(lane: Lane) {
  const markers: Array<{ left: number; symbol: string; events: Event[] }> = [];
  for (const event of [...lane.milestones].sort((a, b) => a.at - b.at)) {
    const positionOnAxis = position(event.at);
    const left = Math.min(98.5, Math.max(1.5, positionOnAxis));
    const previous = markers.at(-1);
    if (previous && left - previous.left < 2.8) {
      previous.events.push(event);
    } else {
      const symbol =
        event.at < bounds.value.start
          ? "‹"
          : event.at > bounds.value.end
            ? "›"
            : "◆";
      markers.push({ left, symbol, events: [event] });
    }
  }
  return markers;
}
function showEvents(lane: Lane, events: Event[]) {
  selection.value = { title: lane.label, details: events.map(eventText) };
  dialogVisible.value = true;
}
function focusSelection() {
  if (selection.value?.at == null) return;
  anchor.value = new Date(selection.value.at).setMinutes(0, 0, 0);
  range.value = "detail";
  dialogVisible.value = false;
}
</script>

<template>
  <div class="plan-timeline">
    <el-form inline class="erp-query-form timeline-controls" @submit.prevent>
      <el-form-item label="视图">
        <el-radio-group v-model="view" aria-label="排程视图">
          <el-radio-button value="order">工单</el-radio-button>
          <el-radio-button value="equipment">设备</el-radio-button>
          <el-radio-button value="person">人员</el-radio-button>
        </el-radio-group>
      </el-form-item>
      <el-form-item label="时间范围">
        <el-select
          :model-value="range"
          class="range-select"
          aria-label="排程时间范围"
          @change="setRange"
        >
          <el-option value="overview" label="整个方案" />
          <el-option value="work" :label="`近看 ${rangeHours.work} 小时`" />
          <el-option value="detail" :label="`放大 ${rangeHours.detail} 小时`" />
        </el-select>
      </el-form-item>
      <el-form-item v-if="range !== 'overview'">
        <el-button :disabled="!canGoBack" @click="move(-1)">上一时段</el-button>
        <el-button :disabled="!canGoForward" @click="move(1)"
          >下一时段</el-button
        >
      </el-form-item>
    </el-form>

    <div v-if="stages.length" class="timeline-caption">
      <span>{{ format(window.start) }} — {{ format(window.end) }}</span>
      <span class="muted">点击条块查看详情</span>
    </div>
    <el-empty
      v-if="!lanes.length"
      :description="
        stages.length ? '当前视图和时段没有排程安排' : '当前条件下没有排程阶段'
      "
    >
      <el-button
        v-if="stages.length && range !== 'overview'"
        @click="setRange('overview')"
      >
        查看整个方案
      </el-button>
    </el-empty>
    <div
      v-else
      class="timeline-scroll"
      :aria-label="`按${viewNames[view]}查看排程`"
      role="region"
    >
      <div class="timeline-body">
        <div class="timeline-row timeline-header">
          <div class="lane-name">{{ viewNames[view] }}</div>
          <div class="timeline-axis">
            <span
              v-for="tick in ticks"
              :key="tick.time"
              class="timeline-tick"
              :style="{ left: `${tick.left}%` }"
              >{{ tick.label }}</span
            >
          </div>
        </div>
        <div v-for="lane in lanes" :key="lane.id" class="timeline-row">
          <div class="lane-name">{{ lane.label }}</div>
          <div class="lane-tracks">
            <i
              v-for="tick in ticks.slice(1)"
              :key="tick.time"
              aria-hidden="true"
              class="timeline-grid"
              :style="{ left: `${tick.left}%` }"
            />
            <div
              v-for="(track, index) in lane.tracks"
              :key="index"
              class="timeline-track"
            >
              <button
                v-for="bar in track"
                :key="bar.stage.segment.id"
                type="button"
                class="stage-bar"
                :class="[
                  `kind-${bar.kind}`,
                  {
                    first: bar.stage.segment.production_phase_code === 'first',
                    supervision:
                      bar.stage.segment.person_capacity_units_snapshot === 1,
                  },
                ]"
                :style="{
                  left: `${position(bar.start)}%`,
                  width: `${position(bar.end) - position(bar.start)}%`,
                }"
                :title="`${barLabel(bar)}\n${barDetails(bar).join('\n')}`"
                :aria-label="`${barLabel(bar)}，${barDetails(bar).join('，')}`"
                @click="showBar(bar)"
              >
                <span class="stage-label">{{ barLabel(bar) }}</span>
              </button>
            </div>
            <div v-if="lane.milestones.length" class="milestone-track">
              <button
                v-for="marker in eventMarkers(lane)"
                :key="marker.left"
                type="button"
                class="milestone"
                :style="{ left: `${marker.left}%` }"
                :title="marker.events.map(eventText).join('\n')"
                :aria-label="marker.events.map(eventText).join('，')"
                @click="showEvents(lane, marker.events)"
              >
                {{ marker.symbol }}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
    <div v-if="lanes.length" class="timeline-legend">
      <span><i class="swatch first" />首件（紫边）</span>
      <span><i class="swatch" />加工 / 人工</span>
      <span><i class="swatch kind-inspection" />检验</span>
      <span><i class="swatch kind-waiting_unload" />占机等待卸料</span>
      <span v-if="view === 'order'"
        ><i class="swatch kind-external_wait" />委外等待</span
      >
      <span v-if="view === 'order'">◆ 放行 / 交期</span>
      <span v-if="view !== 'order'"
        ><i class="swatch supervision" />两机照看</span
      >
      <span v-if="view !== 'order'" class="muted"
        >空白为本方案未安排，可用时间以工作日历为准。</span
      >
    </div>

    <el-dialog
      v-model="dialogVisible"
      :title="selection?.title"
      width="min(520px, 92vw)"
    >
      <ul v-if="selection" class="timeline-details">
        <li v-for="line in selection.details" :key="line">{{ line }}</li>
      </ul>
      <template v-if="selection?.at != null && range !== 'detail'" #footer>
        <el-button type="primary" @click="focusSelection">放大到此处</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.range-select {
  width: 142px;
}

.timeline-caption,
.timeline-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 16px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.timeline-caption {
  justify-content: space-between;
  margin-bottom: 8px;
  font-variant-numeric: tabular-nums;
}

.timeline-scroll {
  max-height: 560px;
  overflow: auto;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
}

.timeline-body {
  --lane-label-width: clamp(136px, 16vw, 210px);

  min-width: calc(var(--lane-label-width) + 680px);
}

.timeline-row {
  display: grid;
  grid-template-columns: var(--lane-label-width) minmax(0, 1fr);
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.timeline-row:last-child {
  border-bottom: none;
}

.timeline-header {
  position: sticky;
  top: 0;
  z-index: 3;
  background: var(--el-fill-color-light);
}

.lane-name {
  position: sticky;
  left: 0;
  z-index: 2;
  display: flex;
  align-items: center;
  padding: 8px 12px;
  overflow-wrap: anywhere;
  background: var(--el-bg-color);
  border-right: 1px solid var(--el-border-color-lighter);
}

.timeline-header .lane-name {
  font-weight: 600;
  background: var(--el-fill-color-light);
}

.lane-tracks,
.timeline-axis,
.timeline-track,
.milestone-track {
  position: relative;
}

.timeline-axis {
  min-height: 36px;
}

.timeline-track {
  height: 36px;
}

.timeline-tick {
  position: absolute;
  padding: 9px 5px;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  color: var(--el-text-color-secondary);
  white-space: nowrap;
}

.timeline-grid {
  position: absolute;
  inset-block: 0;
  border-left: 1px solid var(--el-border-color-lighter);
}

.stage-bar,
.swatch {
  --stage-color: var(--el-color-primary);

  background-color: var(--stage-color);
  border: 0;
  border-radius: 4px;
}

.stage-bar {
  position: absolute;
  top: 5px;
  height: 26px;
  min-width: 1px;
  padding: 0;
  overflow: hidden;
  font-size: 12px;
  font-weight: 500;
  color: var(--el-color-white);
  text-align: left;
  white-space: nowrap;
  cursor: pointer;
  container-type: inline-size;
}

.stage-label {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
}

@container (min-width: 52px) {
  .stage-label {
    padding-inline: 5px;
  }
}

@container (max-width: 51px) {
  .stage-label {
    opacity: 0;
  }
}

.kind-inspection {
  --stage-color: var(--el-color-success);
}
.kind-waiting_unload {
  --stage-color: var(--el-color-warning);
}
.kind-external_wait {
  --stage-color: var(--el-color-info);
}

.first {
  box-shadow: inset 0 0 0 2px #8b5cf6;
}

.supervision {
  background-image: repeating-linear-gradient(
    45deg,
    transparent 0 5px,
    #ffffff38 5px 9px
  );
}

.milestone-track {
  height: 26px;
}

.milestone {
  position: absolute;
  top: 0;
  width: 18px;
  height: 24px;
  padding: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  cursor: pointer;
  background: var(--el-bg-color);
  border: 0;
  transform: translateX(-50%);
}

.stage-bar:focus-visible,
.milestone:focus-visible {
  z-index: 1;
  outline: 2px solid var(--el-color-primary);
  outline-offset: 2px;
}

.timeline-legend {
  margin-top: 12px;
}

.swatch {
  display: inline-block;
  width: 12px;
  height: 8px;
  margin-right: 5px;
  vertical-align: 1px;
}

.timeline-details {
  padding-left: 20px;
  margin: 0;
  line-height: 1.9;
}
</style>
