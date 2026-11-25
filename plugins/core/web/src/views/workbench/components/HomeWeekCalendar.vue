<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRouter } from "vue-router";
import calendarProvider, { type CalendarEvent } from "virtual:workbench-calendar";
import { useUserStoreHook } from "@/store/modules/user";

const today = new Date();
today.setHours(0, 0, 0, 0);
const weekOffset = ref(0);
const selectedDay = ref((today.getDay() + 6) % 7);
const weekdayLabels = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"];
const days = computed(() =>
  weekdayLabels.map((label, index) => {
    const date = new Date(today);
    date.setDate(
      today.getDate() -
        ((today.getDay() + 6) % 7) +
        weekOffset.value * 7 +
        index
    );
    return { label, date, short: `${date.getMonth() + 1}/${date.getDate()}` };
  })
);
const formatDate = (date: Date) =>
  date.toLocaleDateString("zh-CN", {
    year: "numeric",
    month: "long",
    day: "numeric"
  });
const rangeLabel = computed(
  () => `${formatDate(days.value[0].date)} – ${formatDate(days.value[6].date)}`
);
const router = useRouter();
const userStore = useUserStoreHook();
const events = ref<CalendarEvent[]>([]);
const loading = ref(false);
const error = ref(false);
const dateKey = (day: Date) => `${day.getFullYear()}-${String(day.getMonth() + 1).padStart(2, "0")}-${String(day.getDate()).padStart(2, "0")}`;
const selectedEvents = computed(() => events.value.filter(event => event.date === dateKey(days.value[selectedDay.value].date)));
let sequence = 0;
watch([weekOffset, () => userStore.permissions.join("|")], async () => {
  const current = ++sequence;
  events.value = [];
  error.value = false;
  if (!calendarProvider) return;
  loading.value = true;
  try {
    const provider = await calendarProvider();
    const result = await provider.loadEvents(dateKey(days.value[0].date), dateKey(days.value[6].date));
    if (sequence === current) events.value = result;
  } catch {
    if (sequence === current) error.value = true;
  } finally {
    if (sequence === current) loading.value = false;
  }
}, { immediate: true });
</script>

<template>
  <section class="home-calendar" aria-label="近期日程">
    <header class="calendar-heading">
      <h2><IconifyIconOnline icon="ri:calendar-2-line" />近期日程</h2>
    </header>
    <div class="calendar-range">
      <button type="button" aria-label="上一周" @click="weekOffset--">
        <IconifyIconOnline icon="ri:arrow-left-s-line" />
      </button>
      <span>{{ rangeLabel }}</span>
      <button type="button" aria-label="下一周" @click="weekOffset++">
        <IconifyIconOnline icon="ri:arrow-right-s-line" />
      </button>
    </div>
    <div class="calendar-week" role="group" aria-label="选择日期">
      <button
        v-for="(day, index) in days"
        :key="index"
        type="button"
        :class="{ selected: selectedDay === index }"
        :aria-pressed="selectedDay === index"
        :aria-label="formatDate(day.date)"
        @click="selectedDay = index"
      >
        <span>{{ day.label }}</span
        ><strong>{{ day.short }}</strong>
      </button>
    </div>
    <div v-if="selectedEvents.length" class="calendar-events">
      <button v-for="event in selectedEvents" :key="event.id" type="button" @click="router.push(event.path)">
        <strong>{{ event.time }}</strong>
        <div><b>{{ event.title }}</b><p>{{ event.description }}</p></div>
      </button>
    </div>
    <div v-else class="calendar-empty">
      <IconifyIconOnline icon="ri:calendar-schedule-line" />
      <p>{{ formatDate(days[selectedDay].date) }}</p>
      <span>{{ loading ? "正在读取日程…" : error ? "日程读取失败，请稍后重试" : "暂无安排" }}</span>
    </div>
  </section>
</template>

<style lang="scss" scoped>
.home-calendar {
  padding: 18px;
  background: #fff;
  border: 1px solid #e6edf8;
  border-radius: 10px;
}

.calendar-heading {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
}

.calendar-heading h2 {
  display: flex;
  gap: 10px;
  align-items: center;
  margin: 0;
  font-size: 21px;
  color: #100a43;
}

.calendar-heading h2 > svg {
  font-size: 27px;
  color: var(--el-color-primary);
}

.calendar-status {
  font-size: 12px;
  color: #7c83a3;
}

.calendar-range {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: center;
  margin: 16px 0 10px;
  font-size: 12px;
  color: #292453;
}

.calendar-range button {
  display: grid;
  flex: none;
  place-items: center;
  width: 28px;
  height: 28px;
  padding: 0;
  font-size: 20px;
  color: var(--app-button-primary-ink);
  cursor: pointer;
  background: #fff;
  border: 1px solid var(--app-button-primary-border);
  border-radius: 50%;
}

.calendar-week {
  display: grid;
  grid-template-columns: repeat(7, minmax(0, 1fr));
  gap: 4px;
}

.calendar-range button:hover {
  background: var(--app-button-primary-hover-soft);
}

.calendar-week button {
  display: grid;
  gap: 6px;
  justify-items: center;
  padding: 10px 2px;
  font-family: inherit;
  font-size: 12px;
  color: #7c83a3;
  cursor: pointer;
  background: #f7f9fd;
  border: 1px solid transparent;
  border-radius: 7px;
}

.calendar-week strong {
  font-size: 13px;
  font-weight: 500;
}

.calendar-week .selected {
  color: var(--app-button-primary-contrast);
  background: var(--app-button-primary-solid);
}

.calendar-week button:not(.selected):hover {
  color: var(--app-button-primary-ink);
  background: var(--app-button-primary-hover-soft);
}

button:focus-visible {
  outline: 2px solid var(--el-color-primary);
  outline-offset: 2px;
}

.calendar-empty {
  display: grid;
  justify-items: center;
  padding: 24px 0 12px;
  color: #8a90ab;
}

.calendar-empty > svg {
  font-size: 28px;
  color: var(--el-color-primary-light-5);
}

.calendar-empty p {
  margin: 10px 0 4px;
  font-size: 13px;
}

.calendar-empty span {
  font-size: 12px;
}

.calendar-events { display: grid; gap: 10px; margin-top: 16px; max-height: 340px; overflow-y: auto; }
.calendar-events button { display: flex; gap: 12px; padding: 12px; text-align: left; color: #292453; background: #f7f9fd; border: 1px solid #e6edf8; border-radius: 8px; cursor: pointer; }
.calendar-events strong { flex: none; color: var(--el-color-primary); font-size: 13px; }
.calendar-events b { font-size: 14px; }
.calendar-events p { margin: 5px 0 0; font-size: 12px; color: #7c83a3; }
</style>
