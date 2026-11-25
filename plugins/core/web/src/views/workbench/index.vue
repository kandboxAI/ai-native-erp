<script setup lang="ts">
import {
  computed,
  nextTick,
  onActivated,
  onDeactivated,
  onBeforeUnmount,
  onMounted,
  ref,
  watch
} from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { useRoute, useRouter } from "vue-router";
import draggable from "vuedraggable/src/vuedraggable";
import {
  listMyNotices,
  markNoticeRead,
  type SystemNoticeRow
} from "@/api/systemNotice";
import {
  listTodos,
  getTodo,
  recommendTodoPriority,
  type TodoRow
} from "@/api/todo";
import TodoActions from "./components/TodoActions.vue";
import { useTodoRefresh } from "@/utils/todoRefresh";
import {
  getMyUnreadNotificationCount,
  listMyNotifications,
  markNotificationRead,
  type NotificationMineRow
} from "@/api/notificationCenter";
import {
  getUserFavoriteConfig,
  saveUserFavoriteConfig,
  type UserFavoriteConfig,
  type UserFavoriteMenu
} from "@/api/userFavorite";
import { useUserStoreHook } from "@/store/modules/user";
import { getToken, hasPerms } from "@/utils/auth";
import { getHttpErrorMessage } from "@/utils/http";
import { notificationRoute } from "@/utils/notificationRoute";
import { openTodoTarget } from "@/utils/todoTarget";
import { formatTime } from "@/utils/datetime";
import { useAiPageContextStore } from "@/store/modules/aiPageContext";
import type { AiQuestionContext } from "@/utils/aiPageContext";
import {
  desktopAssistantPath,
  registerDesktopAssistant
} from "@/utils/desktopAssistant";
import HomeWeekCalendar from "./components/HomeWeekCalendar.vue";
import SearchModal from "@/layout/components/lay-search/components/SearchModal.vue";

defineOptions({
  name: "PersonalWorkbench"
});
const props = withDefaults(
  defineProps<{ surface?: "home" | "workbench" | "assistant" }>(),
  {
    surface: "workbench"
  }
);
const isHome = computed(() => props.surface === "home");
const branding = __PRODUCT_BRANDING__;

const emit = defineEmits<{
  /** 本机智能体对话面板打开或关闭。 */
  assistantStateChange: [open: boolean];
}>();

type WorkbenchTab = "todos" | "messages" | "announcements" | "favorites";

type FavoriteItem = {
  menuId: string;
  menuKey: string;
  name: string;
  description: string;
  icon: string;
  tone: "blue" | "violet" | "teal" | "orange";
  kind: "系统功能";
  path: string;
};

const router = useRouter();
const route = useRoute();
const userStore = useUserStoreHook();
const isErpDesktop = Boolean(window.erpDesktop);
const assistantOpen = ref(false);
const assistantLeaving = ref(false);
const assistantError = ref("");
const isAgentRoute = computed(
  () =>
    isErpDesktop &&
    props.surface === "assistant" &&
    route.path === desktopAssistantPath
);
watch(assistantOpen, open => emit("assistantStateChange", open), {
  immediate: true
});
const assistantPrompt = ref("");
const menuSearchOpen = ref(false);
const today = new Date();
const workdayLabel = `${today.toLocaleDateString("zh-CN", {
  month: "long",
  day: "numeric"
})} · ${today.toLocaleDateString("zh-CN", { weekday: "long" })}`;
const assistantContext = ref<AiQuestionContext>();
const pageContextStore = useAiPageContextStore();
watch(
  () => pageContextStore.revision,
  () => {
    assistantContext.value = undefined;
    assistantPrompt.value = "";
  }
);
const assistantSurface = ref<HTMLElement | null>(null);
let assistantObserver: ResizeObserver | undefined;
let assistantFrame = 0;
let assistantSettleFrame = 0;
let assistantSettleUntil = 0;
let lastAssistantBounds = "";
let stopAssistantFailure: (() => void) | undefined;
let stopDesktopAssistant: (() => void) | undefined;
let erpSessionReady: Promise<void> = Promise.resolve();

// 原生 DSH 视图总是绘制在 ERP 页面之上，只能占用固定页头以下的可见区域，
// 否则滚动后会盖住标签栏。
function assistantBounds() {
  const surface = assistantSurface.value;
  if (!surface) return;
  const rect = surface.getBoundingClientRect();
  const header = document.querySelector(".fixed-header");
  const top = Math.max(rect.top, header?.getBoundingClientRect().bottom ?? 0);
  const bottom = Math.min(rect.bottom, window.innerHeight);
  return {
    x: rect.left,
    y: top,
    width: rect.width,
    height: Math.max(0, bottom - top)
  };
}

function publishAssistantBounds() {
  if (!assistantOpen.value) return;
  const bounds = assistantBounds();
  if (!bounds) return;
  const boundsKey = [bounds.x, bounds.y, bounds.width, bounds.height]
    .map(Math.round)
    .join(",");
  if (boundsKey === lastAssistantBounds) return;
  lastAssistantBounds = boundsKey;
  void window.erpDesktop?.updateAssistantBounds(bounds);
}

function syncAssistantBounds() {
  if (!assistantOpen.value) return;
  cancelAnimationFrame(assistantFrame);
  assistantFrame = requestAnimationFrame(publishAssistantBounds);
}

function settleAssistantBounds() {
  if (!assistantOpen.value) return;
  publishAssistantBounds();
  if (performance.now() < assistantSettleUntil)
    assistantSettleFrame = requestAnimationFrame(settleAssistantBounds);
}

function startAssistantBoundsSettle() {
  cancelAnimationFrame(assistantSettleFrame);
  assistantSettleUntil = performance.now() + 1200;
  assistantSettleFrame = requestAnimationFrame(settleAssistantBounds);
}

async function closeAssistantView() {
  assistantObserver?.disconnect();
  assistantObserver = undefined;
  cancelAnimationFrame(assistantFrame);
  cancelAnimationFrame(assistantSettleFrame);
  lastAssistantBounds = "";
  await window.erpDesktop?.closeAssistant();
}

async function closeAssistant() {
  if (!assistantOpen.value) return;
  assistantOpen.value = false;
  assistantLeaving.value = false;
  await closeAssistantView();
}

// 路由退出动画仍会展示旧页面；关闭原生视图时先保留智能体布局。
async function closeAssistantForNavigation() {
  if (!assistantOpen.value) return;
  assistantLeaving.value = true;
  try {
    await closeAssistantView();
  } catch (error) {
    assistantLeaving.value = false;
    throw error;
  }
}

async function openDesktopDsh(
  mode: "chat" | "recent",
  prompt?: string,
  context?: AiQuestionContext
): Promise<boolean> {
  const userId = getToken()?.userId;
  try {
    await erpSessionReady;
    if (userId !== getToken()?.userId) throw new Error("Log in to ERP");
    assistantLeaving.value = false;
    assistantError.value = "";
    assistantOpen.value = true;
    await nextTick();
    const bounds = assistantBounds();
    if (!bounds) throw new Error("Assistant surface is unavailable");
    assistantObserver?.disconnect();
    assistantObserver = new ResizeObserver(syncAssistantBounds);
    assistantObserver.observe(assistantSurface.value!);
    lastAssistantBounds = "";
    startAssistantBoundsSettle();
    if (mode === "recent") {
      await window.erpDesktop?.openRecentAssistant(bounds);
    } else {
      await window.erpDesktop?.openAssistant(bounds, prompt, context);
    }
    syncAssistantBounds();
    startAssistantBoundsSettle();
    return true;
  } catch (error) {
    await closeAssistant();
    const message = error instanceof Error ? error.message : String(error);
    assistantError.value = message.includes("(503)")
      ? "智能体服务尚未配置，请联系管理员"
      : message.includes("(401)") || message.includes("Log in to ERP")
        ? "ERP 登录状态已失效，请重新登录"
        : `${branding.assistant_name}暂时无法打开，请稍后重试`;
    ElMessage.error(assistantError.value);
    return false;
  }
}

async function submitDesktopPrompt() {
  const prompt = assistantPrompt.value.trim();
  if (!isErpDesktop || !prompt) return;
  if (await openDesktopDsh("chat", prompt, assistantContext.value)) {
    assistantPrompt.value = "";
    assistantContext.value = undefined;
  }
}
window.addEventListener("resize", syncAssistantBounds);
window.addEventListener("scroll", syncAssistantBounds, true);
onBeforeUnmount(() => {
  stopAssistantFailure?.();
  stopDesktopAssistant?.();
  window.removeEventListener("resize", syncAssistantBounds);
  window.removeEventListener("scroll", syncAssistantBounds, true);
  void closeAssistant();
});
function tabFromQuery(value: unknown): WorkbenchTab {
  if (value === "favorites") return "favorites";
  // 兼容旧书签 tab=notices（原公告表「通知」子类型）
  if (value === "messages" || value === "notices") return "messages";
  if (value === "announcements") return "announcements";
  return "todos";
}

const activeTab = ref<WorkbenchTab>(
  isHome.value
    ? route.query.tab === "announcements" || route.query.tab === "notices"
      ? "announcements"
      : "messages"
    : tabFromQuery(route.query.tab)
);
const keyword = ref("");
const inboxLoading = ref(false);
const todoError = ref("");
const todos = ref<TodoRow[]>([]);
const todoPage = ref(1);
const todoTotal = ref(0);
const messages = ref<NotificationMineRow[]>([]);
const announcements = ref<SystemNoticeRow[]>([]);
const messageUnread = ref(0);
const announcementUnread = ref(0);

const favoriteTones: FavoriteItem["tone"][] = [
  "blue",
  "violet",
  "teal",
  "orange"
];
const favorites = ref<FavoriteItem[]>([]);
const availableFavoriteItems = ref<FavoriteItem[]>([]);
const favoriteDraft = ref<FavoriteItem[]>([]);
const favoriteManagerVisible = ref(false);
const favoriteLoading = ref(false);
const favoriteSaving = ref(false);
const favoriteMaxCount = ref(6);
const favoriteSearch = ref("");
const favoriteCandidateList = ref<HTMLElement>();
const filteredFavoriteItems = computed(() => {
  const search = favoriteSearch.value.trim().toLocaleLowerCase();
  return availableFavoriteItems.value.filter(item =>
    `${item.name} ${item.description}`.toLocaleLowerCase().includes(search)
  );
});
function resetFavoriteScroll() {
  favoriteCandidateList.value?.scrollTo({ top: 0 });
}
watch(favoriteSearch, resetFavoriteScroll);

function favoriteTone(menuKey: string): FavoriteItem["tone"] {
  const hash = [...menuKey].reduce(
    (total, char) => total + char.charCodeAt(0),
    0
  );
  return favoriteTones[hash % favoriteTones.length];
}

function toFavoriteItem(item: UserFavoriteMenu): FavoriteItem {
  return {
    menuId: item.menu_id,
    menuKey: item.menu_key,
    name: item.menu_name,
    description: item.ancestor_names.join(" / ") || "系统功能",
    icon: item.icon || "ri:apps-2-line",
    tone: favoriteTone(item.menu_key),
    kind: "系统功能",
    path: item.path
  };
}

function applyFavoriteConfig(config: UserFavoriteConfig) {
  favorites.value = config.items.map(toFavoriteItem);
  availableFavoriteItems.value = config.candidates.map(toFavoriteItem);
  favoriteMaxCount.value = config.max_count;
}

let favoriteSequence = 0;
async function loadFavorites() {
  if (isHome.value) return;
  const sequence = ++favoriteSequence;
  favoriteLoading.value = true;
  try {
    const response = await getUserFavoriteConfig();
    if (sequence === favoriteSequence && response.code === 0) {
      applyFavoriteConfig(response.data);
    }
  } catch {
    if (sequence === favoriteSequence) {
      favorites.value = [];
      availableFavoriteItems.value = [];
    }
  } finally {
    if (sequence === favoriteSequence) favoriteLoading.value = false;
  }
}

const favoriteDraftIds = computed({
  get: () => favoriteDraft.value.map(item => item.menuId),
  set: (menuIds: string[]) => {
    const selected = new Set(menuIds);
    const retained = favoriteDraft.value.filter(item =>
      selected.has(item.menuId)
    );
    const retainedIds = new Set(retained.map(item => item.menuId));
    favoriteDraft.value = [
      ...retained,
      ...availableFavoriteItems.value.filter(
        item => selected.has(item.menuId) && !retainedIds.has(item.menuId)
      )
    ];
  }
});

const priorityTodos = ref<TodoRow[] | null>(null);
const priorityLoading = ref(false);
const previewTodos = computed(() =>
  (priorityTodos.value ?? todos.value).slice(0, 4)
);
async function rankTodos() {
  priorityLoading.value = true;
  const sequence = inboxSequence;
  try {
    const response = await recommendTodoPriority();
    if (response.code === 0 && sequence === inboxSequence) {
      priorityTodos.value = response.data.items;
      ElMessage.success("已智能排序，原因仅供参考");
    }
  } catch (error) {
    ElMessage.warning(
      getHttpErrorMessage(error, "AI 排序暂不可用，保留原顺序")
    );
  } finally {
    priorityLoading.value = false;
  }
}
const isDetail = computed(
  () =>
    isHome.value ||
    route.query.tab === "favorites" ||
    route.query.tab === "todos" ||
    route.query.tab === "messages" ||
    route.query.tab === "notices" ||
    route.query.tab === "announcements"
);
const includeOverdue = computed(() => !isHome.value && route.query.tab === "todos");

const detailTitle = computed(() => {
  if (activeTab.value === "favorites") return "我的收藏";
  if (activeTab.value === "messages") return "消息";
  if (activeTab.value === "announcements") return "公告";
  return "待办事项";
});

const detailDescription = computed(() => {
  if (activeTab.value === "favorites") return "查看和管理当前收藏的常用入口";
  if (activeTab.value === "messages") return "查看通知中心投递的系统消息";
  if (activeTab.value === "announcements") return "查看已发布的公告与通知文书";
  return "查看需要我处理的业务待办";
});

watch(
  () => route.query.tab,
  value => {
    activeTab.value = isHome.value
      ? value === "announcements" || value === "notices"
        ? "announcements"
        : "messages"
      : tabFromQuery(value);
  },
  { immediate: true }
);

const filteredTodos = computed(() => todos.value);
watch(keyword, () => {
  todoPage.value = 1;
  void loadInbox();
});
watch(todoPage, () => void loadInbox());
watch(
  () => route.query.todo_id,
  async id => {
    if (typeof id !== "string") return;
    try {
      const result = await getTodo(id);
      if (!result.data.targets?.web && !result.data.path) {
        ElMessage.warning(
          result.data.web_unavailable_reason ||
            result.data.summary ||
            "关联记录不可用或无权查看"
        );
        return;
      }
      await openTodoTarget(router, result.data);
    } catch (error) {
      ElMessage.error(getHttpErrorMessage(error, "待办已结束或当前无权查看"));
    }
  },
  { immediate: true }
);

function filterNoticeRows(rows: SystemNoticeRow[]) {
  const query = keyword.value.trim().toLowerCase();
  if (!query) return rows;
  return rows.filter(item =>
    [item.title, item.summary, item.publisher_name_snapshot]
      .filter(Boolean)
      .some(value => String(value).toLowerCase().includes(query))
  );
}

function filterMessageRows(rows: NotificationMineRow[]) {
  const query = keyword.value.trim().toLowerCase();
  if (!query) return rows;
  return rows.filter(item =>
    [item.title, item.content, item.scene_name_snapshot]
      .filter(Boolean)
      .some(value => String(value).toLowerCase().includes(query))
  );
}

const filteredMessages = computed(() => filterMessageRows(messages.value));
const filteredAnnouncements = computed(() =>
  filterNoticeRows(announcements.value)
);

function taskTitle(item: TodoRow) {
  return item.title;
}

function taskMeta(item: TodoRow) {
  return item.summary || item.type_label;
}

function taskPriority(item: TodoRow) {
  if (item.priority_code === "urgent") return "紧急";
  if (item.priority_code === "important") return "重要";
  return "";
}

function taskDeadline(item: TodoRow) {
  if (
    !item.due_at ||
    (!item.is_overdue && (item.todo_type_key === "education.teacher_leave_review" ||
      item.todo_type_key.startsWith("education.schedule_")))
  )
    return "";
  return `截止 ${formatTime(item.due_at)}`;
}

let inboxSequence = 0;
watch(
  // 登录恢复会替换权限数组；只有实际授权变化才重新加载。
  () => JSON.stringify([...userStore.permissions].sort()),
  () => {
    void loadFavorites();
  }
);
let analysisTimer: ReturnType<typeof setTimeout> | undefined;
let inboxActive = true;
watch(activeTab, () => {
  if (isHome.value && inboxActive && route.path === "/welcome") {
    void loadInbox({ refreshTodos: false });
  }
});
function scheduleAnalysisRefresh() {
  clearTimeout(analysisTimer);
  if (
    !inboxActive ||
    !todos.value.some(t =>
      ["pending", "processing"].includes(t.ai_analysis_status_code || "")
    )
  )
    return;
  analysisTimer = setTimeout(async () => {
    const sequence = inboxSequence;
    const token = getToken()?.accessToken;
    if (!token) return;
    try {
      const response = await listTodos({
        page: todoPage.value,
        page_size: 20,
        keyword: keyword.value,
        status_code: "pending",
        include_overdue: includeOverdue.value
      });
      if (
        inboxActive &&
        sequence === inboxSequence &&
        token === getToken()?.accessToken &&
        response.code === 0
      ) {
        todos.value = response.data.items;
        todoTotal.value = response.data.total;
      }
    } catch {
      /* 分析不可用不影响人工审批。 */
    }
    scheduleAnalysisRefresh();
  }, 5000);
}
onActivated(() => {
  if (!inboxActive) void loadInbox();
  inboxActive = true;
  scheduleAnalysisRefresh();
});
onDeactivated(() => {
  inboxActive = false;
  clearTimeout(analysisTimer);
});
onBeforeUnmount(() => {
  inboxActive = false;
  clearTimeout(analysisTimer);
});
async function loadInbox({ refreshTodos = true } = {}) {
  // 首页只展示消息与公告，待办由工作台加载。
  refreshTodos = refreshTodos && !isHome.value;
  if (refreshTodos) {
    todoError.value = "";
    priorityTodos.value = null;
    todos.value = [];
    // 请求完成前保留总数，避免分页控件把当前页重置到第一页。
  }
  const sequence = ++inboxSequence;
  const token = getToken()?.accessToken;
  if (!token) {
    messages.value = [];
    announcements.value = [];
    messageUnread.value = 0;
    announcementUnread.value = 0;
    inboxLoading.value = false;
    return;
  }
  inboxLoading.value = true;
  const [
    todoRes,
    messageRes,
    messageUnreadRes,
    announcementRes,
    announcementUnreadRes
  ] = await Promise.allSettled([
    refreshTodos
      ? listTodos({
          page: todoPage.value,
          page_size: 20,
          status_code: "pending",
          include_overdue: includeOverdue.value,
          keyword: keyword.value
        })
      : Promise.resolve(undefined),
    listMyNotifications({ page: 1, page_size: 50, status_code: "all" }),
    getMyUnreadNotificationCount(),
    listMyNotices({ page: 1, page_size: 50 }),
    listMyNotices({ page: 1, page_size: 1, read_status: "unread" })
  ]);
  if (sequence !== inboxSequence || token !== getToken()?.accessToken) return;
  if (todoRes.status === "fulfilled" && todoRes.value?.code === 0) {
    todos.value = todoRes.value.data.items || [];
    todoTotal.value = todoRes.value.data.total || 0;
    scheduleAnalysisRefresh();
  } else if (refreshTodos) {
    todoError.value = "待办暂时无法加载，请稍后重试或联系管理员";
    todoTotal.value = 0;
  }
  if (messageRes.status === "fulfilled" && messageRes.value.code === 0) {
    messages.value = messageRes.value.data.items || [];
  }
  if (
    messageUnreadRes.status === "fulfilled" &&
    messageUnreadRes.value.code === 0
  ) {
    messageUnread.value = messageUnreadRes.value.data.unread_count || 0;
  }
  if (
    announcementRes.status === "fulfilled" &&
    announcementRes.value.code === 0
  ) {
    announcements.value = announcementRes.value.data.items || [];
  }
  if (
    announcementUnreadRes.status === "fulfilled" &&
    announcementUnreadRes.value.code === 0
  ) {
    announcementUnread.value = announcementUnreadRes.value.data.total || 0;
  }
  inboxLoading.value = false;
}

function openPath(path: string) {
  router.push(path);
}

function openFavorite(item: FavoriteItem) {
  openPath(item.path);
}

function openFavoriteManager() {
  favoriteDraft.value = favorites.value.map(item => ({ ...item }));
  favoriteSearch.value = "";
  favoriteManagerVisible.value = true;
}

async function saveFavorites() {
  favoriteSaving.value = true;
  try {
    const response = await saveUserFavoriteConfig(
      favoriteDraft.value.map(item => item.menuId)
    );
    if (response.code === 0) {
      applyFavoriteConfig(response.data);
      favoriteManagerVisible.value = false;
      ElMessage.success(response.message || "收藏已更新");
    }
  } finally {
    favoriteSaving.value = false;
  }
}

function openAllTodos() {
  router.push({ path: "/workbench", query: { tab: "todos" } });
}

function openFavoritesDetail() {
  router.push({
    path: "/workbench",
    query: { tab: "favorites" }
  });
}

function switchWorkbenchTab(tab: WorkbenchTab) {
  router.push({
    path:
      tab === "messages" || tab === "announcements" ? "/welcome" : "/workbench",
    query: { tab }
  });
}

async function openAnnouncement(row: SystemNoticeRow) {
  if (!row.is_read) {
    try {
      await markNoticeRead(row.id);
      row.is_read = true;
      announcementUnread.value = Math.max(0, announcementUnread.value - 1);
    } catch {
      /* 已读回写失败时仍允许查看 */
    }
  }
}

async function openMessage(row: NotificationMineRow) {
  if (row.status_code === "unread") {
    try {
      await markNotificationRead(row.recipient_id);
      row.status_code = "read";
      messageUnread.value = Math.max(0, messageUnread.value - 1);
    } catch {
      /* 已读回写失败时仍允许查看 */
    }
  }
  router.push(notificationRoute(row, router));
}

function backToOverview() {
  router.push("/workbench");
}

function activateAssistantPage() {
  if (!isAgentRoute.value || stopDesktopAssistant) return;
  let receivedRequest = false;
  stopDesktopAssistant = registerDesktopAssistant(request => {
    receivedRequest = true;
    const prompt = request.kind === "question" ? request.prompt : undefined;
    void openDesktopDsh(
      request.kind === "recent" ? "recent" : "chat",
      prompt,
      request.kind === "question" ? request.context : undefined
    ).then(opened => {
      if (opened) {
        assistantContext.value = undefined;
        assistantPrompt.value = "";
      }
      if (
        !opened &&
        prompt &&
        request.kind === "question" &&
        request.userId === getToken()?.userId
      ) {
        assistantPrompt.value = prompt;
        assistantContext.value =
          request.kind === "question" ? request.context : undefined;
      }
    });
  }, closeAssistantForNavigation);
  // 固定页签或地址栏直接进入时没有待处理问题，主动恢复最近会话。
  if (!receivedRequest) void openDesktopDsh("recent");
}

function deactivateAssistantPage() {
  stopDesktopAssistant?.();
  stopDesktopAssistant = undefined;
  void closeAssistant();
}

onActivated(activateAssistantPage);
onDeactivated(deactivateAssistantPage);

onMounted(() => {
  void loadFavorites();
  const accessToken = getToken()?.accessToken;
  if (accessToken)
    erpSessionReady =
      window.erpDesktop
        ?.bindErpSession(accessToken)
        .catch(() => undefined) ?? Promise.resolve();
  activateAssistantPage();
  stopAssistantFailure = window.erpDesktop?.onAssistantFailed(() => {
    void closeAssistant();
    assistantError.value = `${branding.assistant_name}启动失败，请稍后重试`;
    ElMessage.error(assistantError.value);
  });
});
useTodoRefresh(() => void loadInbox());
</script>

<template>
  <section class="personal-workbench">
    <div class="workbench-shell">
      <section
        v-if="assistantOpen || isAgentRoute"
        class="desktop-assistant-panel"
      >
        <div ref="assistantSurface" class="desktop-assistant-surface">
          <div v-if="assistantError" class="desktop-assistant-error">
            <p>{{ assistantError }}</p>
            <button type="button" @click="openDesktopDsh('recent')">
              重试
            </button>
          </div>
          <template v-else>
            {{
              assistantLeaving
                ? "正在返回管理界面…"
                : `正在打开${branding.assistant_name}…`
            }}
          </template>
        </div>
      </section>

      <section v-else-if="isDetail" class="detail-heading">
        <div>
          <button
            v-if="!isHome"
            type="button"
            class="back-button"
            @click="backToOverview"
          >
            <IconifyIconOnline icon="ri:arrow-left-line" />
            返回待办总览
          </button>
          <h1>{{ isHome ? "消息与公告" : detailTitle }}</h1>
          <p>{{ isHome ? "查看我的消息与学校公告" : detailDescription }}</p>
        </div>
        <div class="detail-summary">
          <span v-if="!isHome">
            {{
              todoError
                ? "待办加载失败"
                : inboxLoading
                  ? "正在加载待办"
                  : "全部待办"
            }}
            <b v-if="!todoError && !inboxLoading">{{ todoTotal }}</b>
          </span>
          <span v-if="isHome"
            >未读消息 <b>{{ messageUnread }}</b></span
          >
          <span v-if="isHome"
            >未读公告 <b>{{ announcementUnread }}</b></span
          >
        </div>
      </section>

      <section v-else v-loading="inboxLoading" class="overview-content">
        <section class="desktop-dsh-panel">
          <header class="desktop-dsh-heading">
            <h1>今日工作，从这里开始</h1>
            <span>{{ workdayLabel }}</span>
          </header>
          <div class="desktop-dsh-entry">
            <SearchModal
              v-model:value="menuSearchOpen"
              v-model:keyword="assistantPrompt"
              inline
              @ask="submitDesktopPrompt"
            >
              <template
                #entry="{
                  keyword: searchKeyword,
                  setKeyword,
                  openSearch,
                  handleEnter,
                  handleUp,
                  handleDown,
                  handleClose
                }"
              >
                <form
                  class="desktop-dsh-question"
                  @submit.prevent="handleEnter"
                >
                  <span class="desktop-dsh-question-symbol" aria-hidden="true">
                    <svg viewBox="0 0 32 32" fill="currentColor">
                      <path
                        d="M16 1C18.2 11.1 20.9 13.8 31 16C20.9 18.2 18.2 20.9 16 31C13.8 20.9 11.1 18.2 1 16C11.1 13.8 13.8 11.1 16 1Z"
                      />
                    </svg>
                  </span>
                  <input
                    :value="searchKeyword"
                    data-menu-search-input
                    :aria-label="
                      isErpDesktop
                        ? '搜索已授权菜单或询问 AI'
                        : '搜索已授权菜单'
                    "
                    autocomplete="off"
                    :placeholder="
                      isErpDesktop
                        ? `搜服务、查制度、问${branding.assistant_name}`
                        : '搜索菜单或服务'
                    "
                    @input="
                      setKeyword(($event.target as HTMLInputElement).value)
                    "
                    @focus="openSearch"
                    @click="openSearch"
                    @keydown.down.prevent="handleDown"
                    @keydown.up.prevent="handleUp"
                    @keydown.esc.prevent="handleClose"
                  />
                  <kbd class="desktop-dsh-shortcut">Ctrl / ⌘ K</kbd>
                  <button class="desktop-dsh-search-button" type="submit">
                    <IconifyIconOnline
                      icon="ri:search-line"
                      aria-hidden="true"
                    />
                    <span>搜索</span>
                  </button>
                </form>
              </template>
            </SearchModal>
            <p
              v-if="isErpDesktop && assistantContext"
              class="desktop-dsh-context"
            >
              将携带：{{ assistantContext.title }} ›
              {{ assistantContext.subject_title }}
              <el-button
                data-action="neutral"
                link
                type="primary"
                @click="assistantContext = undefined"
                >移除上下文</el-button
              >
            </p>
            <div v-if="isErpDesktop" class="desktop-dsh-footer">
              <p class="desktop-dsh-hint">
                <IconifyIconOnline
                  icon="ri:information-line"
                  aria-hidden="true"
                />
                AI 建议附来源，重要操作由你确认。
              </p>
              <div class="desktop-dsh-links">
                <button type="button" @click="openDesktopDsh('recent')">
                  <IconifyIconOnline icon="ri:history-line" />
                  继续最近会话
                </button>
              </div>
            </div>
          </div>
        </section>
        <div class="home-overview">
          <div class="home-column home-primary">
            <section
              v-loading="inboxLoading"
              class="home-panel home-priority-panel"
            >
              <header class="home-panel-heading">
                <h2><IconifyIconOnline icon="ri:list-check" />优先处理</h2>
                <el-button
                  type="primary"
                  link
                  size="small"
                  :loading="priorityLoading"
                  :disabled="!todoTotal || inboxLoading"
                  @click="rankTodos"
                >
                  AI 智能排序
                </el-button>
                <button
                  v-if="!todoError"
                  type="button"
                  class="home-priority-summary"
                  @click="openAllTodos"
                >
                  <template v-if="inboxLoading">正在加载待办</template>
                  <template v-else
                    >共 {{ todoTotal }} 项待办 · 查看全部</template
                  >
                  <IconifyIconOnline icon="ri:arrow-right-s-line" />
                </button>
              </header>
              <p v-if="priorityTodos" class="task-ai-pending">
                AI 建议仅供参考<span v-if="todoTotal > 100"
                  >，本次从原排序前 100 项中推荐</span
                >
              </p>
              <p
                v-else-if="todoTotal && !inboxLoading && !todoError"
                class="task-ai-pending"
              >
                按紧急程度、截止时间排序
              </p>
              <div v-if="todoError" class="home-panel-empty" role="alert">
                <IconifyIconOnline icon="ri:error-warning-line" />
                <p>{{ todoError }}</p>
                <el-button :disabled="inboxLoading" @click="loadInbox()">
                  重新加载
                </el-button>
              </div>
              <div v-else-if="previewTodos.length" class="home-priority-list">
                <article
                  v-for="item in previewTodos"
                  :key="item.id"
                  class="home-priority-item"
                >
                  <el-avatar
                    v-if="item.avatar_url"
                    :src="item.avatar_url"
                    :size="48"
                    class="home-task-avatar"
                  />
                  <span v-else class="home-task-icon">
                    <IconifyIconOnline icon="ri:file-list-3-line" />
                  </span>
                  <div class="home-task-copy">
                    <div class="home-task-title">
                      <h3>{{ taskTitle(item) }}</h3>
                      <span class="home-task-status">{{
                        taskPriority(item) || "待处理"
                      }}</span>
                    </div>
                    <p class="task-facts">{{ taskMeta(item) }}</p>
                    <p v-if="item.ai_priority_reason" class="task-ai-analysis">
                      <span>优先原因</span>{{ item.ai_priority_reason }}
                    </p>
                    <p v-if="item.ai_analysis" class="task-ai-analysis">
                      <span>AI分析</span>{{ item.ai_analysis }}
                    </p>
                    <p
                      v-else-if="
                        ['pending', 'processing'].includes(
                          item.ai_analysis_status_code || ''
                        )
                      "
                      class="task-ai-pending"
                    >
                      AI分析中…
                    </p>
                    <p
                      v-else-if="item.ai_analysis_status_code === 'failed'"
                      class="task-ai-pending"
                    >
                      AI分析暂不可用，可查看材料人工审批
                    </p>

                    <div class="todo-meta">
                      <span v-if="taskDeadline(item)">{{
                        taskDeadline(item)
                      }}</span>
                      <span v-if="item.arrived_at"
                        ><IconifyIconOnline icon="ri:time-line" />收到
                        {{ formatTime(item.arrived_at) }}</span
                      >
                    </div>
                  </div>
                  <TodoActions :item="item" @changed="loadInbox" />
                </article>
              </div>
              <div v-else-if="!inboxLoading" class="home-panel-empty">
                <IconifyIconOnline icon="ri:checkbox-circle-line" />
                <p>暂无待办</p>
                <p>分配给你的待办事项会显示在这里</p>
              </div>
            </section>
          </div>
          <div class="home-column home-secondary">
            <section
              v-loading="favoriteLoading"
              class="home-panel home-business-panel"
            >
              <slot name="common-business">
                <header class="home-panel-heading">
                  <h2><IconifyIconOnline icon="ri:apps-2-line" />常用业务</h2>
                  <button type="button" @click="openFavoritesDetail">
                    管理收藏<IconifyIconOnline icon="ri:arrow-right-s-line" />
                  </button>
                </header>
                <div class="home-business-grid">
                  <button
                    v-for="item in favorites"
                    :key="item.path"
                    type="button"
                    @click="openFavorite(item)"
                  >
                    <IconifyIconOnline :icon="item.icon" />
                    <strong>{{ item.name }}</strong
                    ><small>{{ item.description }}</small>
                  </button>
                </div>
                <p v-if="!favorites.length" class="overview-empty">
                  暂未收藏常用入口
                </p>
              </slot>
              <button
                class="home-favorites-link"
                type="button"
                @click="openFavoritesDetail"
              >
                我的收藏 / 管理
              </button>
            </section>
            <HomeWeekCalendar />
          </div>
        </div>
      </section>

      <section v-if="isDetail" class="workspace-card">
        <div class="workspace-tabs" role="tablist" aria-label="个人工作台">
          <button
            v-if="!isHome"
            :class="{ active: activeTab === 'todos' }"
            type="button"
            role="tab"
            :aria-selected="activeTab === 'todos'"
            @click="switchWorkbenchTab('todos')"
          >
            <IconifyIconOnline icon="ri:checkbox-circle-line" />
            待办事项
            <em>{{ todoTotal }}</em>
          </button>
          <button
            v-if="isHome"
            :class="{ active: activeTab === 'messages' }"
            type="button"
            role="tab"
            :aria-selected="activeTab === 'messages'"
            @click="switchWorkbenchTab('messages')"
          >
            <IconifyIconOnline icon="ri:notification-3-line" />
            消息
            <em>{{ messageUnread }}</em>
          </button>
          <button
            v-if="isHome"
            :class="{ active: activeTab === 'announcements' }"
            type="button"
            role="tab"
            :aria-selected="activeTab === 'announcements'"
            @click="switchWorkbenchTab('announcements')"
          >
            <IconifyIconOnline icon="ri:megaphone-line" />
            公告
            <em>{{ announcementUnread }}</em>
          </button>
          <button
            v-if="!isHome"
            :class="{ active: activeTab === 'favorites' }"
            type="button"
            role="tab"
            :aria-selected="activeTab === 'favorites'"
            @click="switchWorkbenchTab('favorites')"
          >
            <IconifyIconOnline icon="ri:star-line" />
            我的收藏
            <em>{{ favorites.length }}</em>
          </button>
        </div>

        <div v-if="activeTab === 'todos'" class="todo-section">
          <div class="toolbar">
            <el-input
              v-model="keyword"
              clearable
              class="todo-search"
              placeholder="搜索待办事项"
            >
              <template #prefix>
                <IconifyIconOnline icon="ri:search-line" />
              </template>
            </el-input>
          </div>

          <div v-loading="inboxLoading" class="todo-list">
            <article
              v-for="item in filteredTodos"
              :key="item.id"
              class="todo-item"
            >
              <span class="todo-item-icon">
                <IconifyIconOnline icon="ri:checkbox-circle-line" />
              </span>
              <div class="todo-copy">
                <div class="todo-title-row">
                  <h2>{{ taskTitle(item) }}</h2>
                  <el-tag v-if="item.is_overdue" type="danger" effect="light" size="small">逾期</el-tag>
                  <span v-if="taskPriority(item)" class="home-task-status">{{
                    taskPriority(item)
                  }}</span>
                </div>
                <p class="task-facts">{{ taskMeta(item) }}</p>
                <p v-if="item.ai_analysis" class="task-ai-analysis">
                  <span>AI分析</span>{{ item.ai_analysis }}
                </p>
                <p
                  v-else-if="
                    ['pending', 'processing'].includes(
                      item.ai_analysis_status_code || ''
                    )
                  "
                  class="task-ai-pending"
                >
                  AI分析中…
                </p>
                <p
                  v-else-if="item.ai_analysis_status_code === 'failed'"
                  class="task-ai-pending"
                >
                  AI分析暂不可用，可查看材料人工审批
                </p>

                <div class="todo-meta">
                  <span v-if="taskDeadline(item)">{{
                    taskDeadline(item)
                  }}</span>
                  <span v-if="item.arrived_at"
                    ><IconifyIconOnline icon="ri:time-line" />收到
                    {{ formatTime(item.arrived_at) }}</span
                  >
                </div>
              </div>
              <TodoActions :item="item" @changed="loadInbox" />
            </article>
            <div v-if="todoError" class="empty-state" role="alert">
              <IconifyIconOnline icon="ri:error-warning-line" />
              <strong>{{ todoError }}</strong>
              <el-button :disabled="inboxLoading" @click="loadInbox()">
                重新加载
              </el-button>
            </div>
            <div
              v-else-if="!inboxLoading && filteredTodos.length === 0"
              class="empty-state"
            >
              <IconifyIconOnline icon="ri:inbox-2-line" />
              <strong>暂无待办</strong>
            </div>
          </div>
          <ReListPagination
            v-if="!todoError"
            v-model:current-page="todoPage"
            :page-size="20"
            :total="todoTotal"
          />
        </div>

        <div v-else-if="activeTab === 'messages'" class="todo-section">
          <div v-loading="inboxLoading" class="todo-list">
            <article
              v-for="item in filteredMessages"
              :key="item.recipient_id"
              class="todo-item"
              @click="openMessage(item)"
            >
              <span class="todo-item-icon">
                <IconifyIconOnline icon="ri:notification-3-line" />
              </span>
              <div class="todo-copy">
                <div class="todo-title-row">
                  <h2>{{ item.title }}</h2>
                  <span
                    v-if="item.status_code === 'unread'"
                    class="status-tag status-unread"
                    >未读</span
                  >
                </div>
                <p>{{ item.content || item.scene_name_snapshot || "消息" }}</p>
                <div class="todo-meta">
                  <span>{{ item.scene_name_snapshot || "消息" }}</span>
                  <span
                    ><IconifyIconOnline icon="ri:time-line" />
                    {{ formatTime(item.occurred_at || item.created_at) }}</span
                  >
                </div>
              </div>
            </article>
            <div v-if="filteredMessages.length === 0" class="empty-state">
              <IconifyIconOnline icon="ri:inbox-2-line" />
              <strong>暂无消息</strong>
            </div>
          </div>
        </div>

        <div v-else-if="activeTab === 'announcements'" class="todo-section">
          <div v-loading="inboxLoading" class="todo-list">
            <article
              v-for="item in filteredAnnouncements"
              :key="item.id"
              class="todo-item"
              @click="openAnnouncement(item)"
            >
              <span class="todo-item-icon">
                <IconifyIconOnline icon="ri:megaphone-line" />
              </span>
              <div class="todo-copy">
                <div class="todo-title-row">
                  <h2>{{ item.title }}</h2>
                  <span v-if="!item.is_read" class="status-tag status-unread"
                    >未读</span
                  >
                </div>
                <p>{{ item.summary || "公告" }}</p>
                <div class="todo-meta">
                  <span>{{
                    item.notice_type_code === "notice" ? "通知" : "公告"
                  }}</span>
                  <span
                    ><IconifyIconOnline icon="ri:time-line" />
                    {{ formatTime(item.published_at || item.created_at) }}</span
                  >
                </div>
              </div>
            </article>
            <div v-if="filteredAnnouncements.length === 0" class="empty-state">
              <IconifyIconOnline icon="ri:inbox-2-line" />
              <strong>暂无公告</strong>
            </div>
          </div>
        </div>

        <div v-else v-loading="favoriteLoading" class="favorite-section">
          <div class="favorite-heading">
            <div>
              <h2>常用入口</h2>
              <p>集中访问常用系统功能和外部服务。</p>
            </div>
            <el-button
              data-action="primary"
              type="primary"
              plain
              @click="openFavoriteManager"
            >
              <IconifyIconOnline icon="ri:settings-4-line" />
              管理收藏
            </el-button>
          </div>
          <div class="favorite-grid">
            <button
              v-for="item in favorites"
              :key="item.path"
              class="favorite-card"
              type="button"
              @click="openFavorite(item)"
            >
              <span :class="['favorite-icon', `tone-${item.tone}`]">
                <IconifyIconOnline :icon="item.icon" />
              </span>
              <span class="favorite-copy">
                <strong>{{ item.name }}</strong>
                <small>{{ item.description }}</small>
              </span>
              <span class="favorite-type">{{ item.kind }}</span>
              <IconifyIconOnline
                class="favorite-arrow"
                icon="ri:arrow-right-line"
              />
            </button>
            <div v-if="favorites.length === 0" class="favorite-empty">
              <IconifyIconOnline icon="ri:star-line" />
              <strong>暂未添加收藏</strong>
              <span>点击“管理收藏”从有权访问的菜单中选择。</span>
            </div>
          </div>
        </div>
      </section>
    </div>

    <el-dialog
      v-model="favoriteManagerVisible"
      title="管理我的收藏"
      width="min(960px, calc(100vw - 32px))"
      class="favorite-manager-dialog"
      align-center
      @opened="resetFavoriteScroll"
    >
      <p class="manager-tip">
        最多选择 {{ favoriteMaxCount }} 个入口；拖动已选菜单可调整首页顺序。
      </p>
      <section class="manager-selected">
        <div class="manager-subheading">
          <strong>已选收藏</strong>
          <span>{{ favoriteDraft.length }} / {{ favoriteMaxCount }}</span>
        </div>
        <draggable
          v-if="favoriteDraft.length"
          v-model="favoriteDraft"
          item-key="menuId"
          handle=".manager-drag-handle"
          class="manager-sort-list"
          ghost-class="manager-sort-ghost"
        >
          <template #item="{ element }">
            <div class="manager-sort-item">
              <IconifyIconOnline
                class="manager-drag-handle"
                icon="ri:draggable"
              />
              <span :class="['manager-icon', `tone-${element.tone}`]">
                <IconifyIconOnline :icon="element.icon" />
              </span>
              <span class="manager-sort-copy">
                <strong :title="`${element.name} · ${element.description}`">
                  {{ element.name }}
                </strong>
              </span>
              <el-button
                data-action="neutral"
                class="manager-remove"
                text
                circle
                :aria-label="`移除${element.name}`"
                :disabled="favoriteSaving"
                @click="
                  favoriteDraftIds = favoriteDraftIds.filter(
                    id => id !== element.menuId
                  )
                "
              >
                <IconifyIconOnline icon="ri:close-line" />
              </el-button>
            </div>
          </template>
        </draggable>
        <div v-else class="manager-selected-empty">尚未选择收藏菜单</div>
      </section>
      <div class="manager-candidate-toolbar">
        <div class="manager-subheading manager-candidate-heading">
          <strong>可收藏菜单</strong>
          <span
            >仅显示有权访问的菜单 · {{ filteredFavoriteItems.length }} 项</span
          >
        </div>
        <el-input
          v-model="favoriteSearch"
          class="manager-search"
          placeholder="搜索菜单名称或所属模块"
          aria-label="搜索可收藏菜单"
          clearable
        >
          <template #prefix>
            <IconifyIconOnline icon="ri:search-line" />
          </template>
        </el-input>
      </div>
      <div
        ref="favoriteCandidateList"
        class="manager-candidates pure-scrollbar"
        tabindex="0"
        aria-label="可收藏菜单列表"
      >
        <el-checkbox-group
          v-model="favoriteDraftIds"
          :max="favoriteMaxCount"
          class="manager-grid"
        >
          <el-checkbox
            v-for="item in filteredFavoriteItems"
            :key="item.menuId"
            :value="item.menuId"
            class="manager-option"
          >
            <span :class="['manager-icon', `tone-${item.tone}`]">
              <IconifyIconOnline :icon="item.icon" />
            </span>
            <span>
              <strong :title="item.name">{{ item.name }}</strong>
              <small :title="item.description">{{ item.description }}</small>
            </span>
          </el-checkbox>
        </el-checkbox-group>
        <div
          v-if="filteredFavoriteItems.length === 0"
          class="manager-selected-empty"
        >
          {{
            availableFavoriteItems.length
              ? "未找到匹配的菜单，请尝试其他关键词"
              : "当前账号暂无可收藏菜单"
          }}
        </div>
      </div>
      <template #footer>
        <el-button
          data-action="neutral"
          :disabled="favoriteSaving"
          @click="favoriteManagerVisible = false"
        >
          取消
        </el-button>
        <el-button
          data-action="primary"
          :loading="favoriteSaving"
          type="primary"
          @click="saveFavorites"
        >
          保存收藏
        </el-button>
      </template>
    </el-dialog>
  </section>
</template>

<style scoped lang="scss">
.task-ai-analysis {
  overflow: visible;
  text-overflow: clip;
  font-size: 12px !important;
  line-height: 1.7;
  color: #6d4cb1 !important;
  white-space: normal;
}

.task-ai-analysis span {
  display: inline-block;
  padding: 0 5px;
  margin-right: 8px;
  font-size: 11px;
  color: #7854bb;
  background: #f0eaff;
  border-radius: 4px;
}

.task-ai-pending {
  font-size: 12px !important;
  color: #8a96a7 !important;
}

.desktop-assistant-panel {
  overflow: hidden;
  background: #fff;
  border: 1px solid #d8e4f2;
  border-radius: 18px;
  box-shadow: 0 15px 38px rgb(24 69 128 / 10%);
}

.desktop-assistant-surface {
  height: max(0px, calc(100dvh - 88px));
  background: #fff;
}

.desktop-assistant-error {
  display: flex;
  flex-direction: column;
  gap: 12px;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #687b95;
}

.desktop-assistant-error button {
  padding: 8px 18px;
  color: var(--app-button-primary-contrast);
  cursor: pointer;
  background: var(--app-button-primary-solid);
  border: 0;
  border-radius: 8px;
}

.desktop-dsh-panel {
  display: grid;
  gap: 12px;
}

.desktop-dsh-heading {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 24px;
  align-items: baseline;
  justify-content: space-between;
  color: #100a43;
}

.desktop-dsh-heading h1 {
  margin: 0;
  font-size: 28px;
  font-weight: 700;
  line-height: 1.4;
}

.desktop-dsh-heading > span {
  font-size: 14px;
  color: #617591;
}

.desktop-dsh-hint {
  display: flex;
  gap: 6px;
  align-items: center;
  margin: 0;
  font-size: 14px;
  line-height: 22px;
  color: #7c83a3;
}

.desktop-dsh-hint > svg {
  flex: none;
  font-size: 18px;
}

.desktop-dsh-footer {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 16px;
  align-items: center;
  justify-content: space-between;
  margin-top: 4px;
}

.desktop-dsh-links {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 16px;
  margin-left: auto;
}

.desktop-dsh-links button {
  display: inline-flex;
  gap: 5px;
  align-items: center;
  padding: 0;
  font-size: 12px;
  line-height: 22px;
  color: var(--app-button-primary-ink);
  cursor: pointer;
  background: transparent;
  border: 0;
}

.desktop-dsh-links button:hover {
  color: var(--el-color-primary-light-3);
}

.desktop-dsh-links button:focus-visible {
  outline: 2px solid var(--el-color-primary);
  outline-offset: 3px;
}

.desktop-dsh-entry {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
  min-width: 0;
}

.desktop-dsh-question {
  display: flex;
  gap: 14px;
  align-items: center;
  min-height: 52px;
  padding: 6px;
  color: var(--el-color-primary);
  background: #fff;
  border: 1px solid var(--el-color-primary);
  border-radius: 8px;
  box-shadow: 0 0 0 3px var(--el-color-primary-light-9);
  transition: box-shadow 0.2s;
}

.desktop-dsh-question:focus-within {
  box-shadow: 0 0 0 3px var(--el-color-primary-light-7);
}

.desktop-dsh-question-symbol {
  display: grid;
  flex: none;
  place-items: center;
  width: 60px;
  height: 28px;
  border-right: 1px solid #e2e8f0;
}

.desktop-dsh-question-symbol svg {
  width: 32px;
  height: 32px;
}

.desktop-dsh-question input {
  flex: 1;
  min-width: 0;
  padding: 8px 0;
  font-family: inherit;
  font-size: 20px;
  line-height: 28px;
  color: #193655;
  outline: 0;
  background: transparent;
  border: 0;
}

.desktop-dsh-question input::placeholder {
  color: #7c83a3;
}

.desktop-dsh-shortcut {
  flex: none;
  padding: 3px 6px;
  font-family: inherit;
  font-size: 12px;
  color: #7c83a3;
  border: 1px solid #e2e8f0;
  border-radius: 4px;
}

.desktop-dsh-search-button {
  display: inline-flex;
  flex: none;
  gap: 10px;
  align-items: center;
  justify-content: center;
  width: 150px;
  height: 38px;
  font-size: 20px;
  font-weight: 500;
  color: var(--app-button-primary-contrast);
  cursor: pointer;
  background: var(--app-button-primary-solid);
  border: 0;
  border-radius: 8px;
  transition: background-color 0.2s;
}

.desktop-dsh-search-button > svg {
  font-size: 24px;
}

.desktop-dsh-search-button:hover {
  color: var(--app-button-primary-hover-contrast);
  background: var(--app-button-primary-hover-solid);
}

.desktop-dsh-search-button:active {
  color: var(--app-button-primary-active-contrast);
  background: var(--app-button-primary-active-solid);
}

.desktop-dsh-search-button:focus-visible {
  outline: 2px solid var(--el-color-primary);
  outline-offset: 2px;
}

@media (width <= 780px) {
  .desktop-dsh-heading {
    flex-direction: column;
    gap: 3px;
  }

  .desktop-dsh-shortcut {
    display: none;
  }

  .desktop-dsh-heading h1 {
    font-size: 26px;
  }

  .desktop-dsh-heading > span {
    font-size: 14px;
  }

  .desktop-dsh-question {
    gap: 8px;
  }

  .desktop-dsh-question-symbol {
    width: 38px;
  }

  .desktop-dsh-question-symbol svg {
    width: 26px;
    height: 26px;
  }

  .desktop-dsh-question input {
    font-size: 16px;
  }

  .desktop-dsh-search-button {
    gap: 6px;
    width: 88px;
    font-size: 16px;
  }
}

.personal-workbench {
  --navy: #173b68;
  --blue: var(--el-color-primary);
  --muted: #728198;

  color: #193655;
}

button {
  font: inherit;
}

.workbench-shell {
  width: 100%;
}

.overview-content {
  display: grid;
  gap: 18px;
}

.home-overview {
  display: grid;
  grid-template-rows: auto auto;
  grid-template-columns: minmax(0, 1.65fr) minmax(0, 1fr);
  gap: 16px;
  align-items: stretch;
}

.home-column {
  display: grid;
  grid-template-rows: subgrid;
  grid-row: 1 / span 2;
  gap: 16px;
  min-width: 0;
}

.home-primary {
  grid-column: 1;
}

.home-priority-panel {
  grid-row: 1 / -1;
}

.home-secondary {
  grid-column: 2;
}

.home-panel {
  min-width: 0;
  padding: 18px;
  background: #fff;
  border: 1px solid #e6edf8;
  border-radius: 10px;
}

.home-panel-heading {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 12px;
  align-items: center;
  justify-content: space-between;
  min-height: 50px;
  padding-bottom: 14px;
  border-bottom: 1px solid #edf1f8;
}

.home-panel-heading h2 {
  display: flex;
  gap: 10px;
  align-items: center;
  margin: 0;
  font-size: 21px;
  color: #100a43;
}

.home-panel-heading h2 > svg {
  font-size: 26px;
  color: var(--el-color-primary);
}

.home-panel-heading button,
.home-favorites-link {
  display: inline-flex;
  gap: 4px;
  align-items: center;
  padding: 0;
  font-size: 12px;
  color: var(--app-button-primary-ink);
  cursor: pointer;
  background: transparent;
  border: 0;
}

.home-panel-heading .home-priority-summary {
  padding: 8px 10px;
  color: var(--app-button-primary-ink);
  background: var(--app-button-primary-soft);
  border-radius: 8px;
}

.home-priority-item {
  display: flex;
  gap: 16px;
  align-items: center;
  min-height: 100px;
  padding: 16px 0;
  border-bottom: 1px solid #edf1f8;
}

.home-priority-item:last-child {
  padding-bottom: 4px;
  border-bottom: 0;
}

.home-task-avatar {
  flex-shrink: 0;
}

.home-task-icon {
  display: grid;
  flex: none;
  place-items: center;
  width: 58px;
  height: 58px;
  font-size: 30px;
  color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
  border-radius: 50%;
}

.home-task-copy {
  flex: 1;
  min-width: 0;
}

.home-task-title {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 10px;
  align-items: center;
}

.home-task-title h3 {
  min-width: 0;
  margin: 0;
  font-size: 16px;
  color: #171244;
  overflow-wrap: anywhere;
}

.home-task-status {
  padding: 3px 10px;
  font-size: 12px;
  color: #326cff;
  background: #edf3ff;
  border-radius: 20px;
}

.home-task-copy p {
  margin: 6px 0;
  font-size: 12px;
  color: #7c83a3;
}

.task-actions {
  display: flex;
  flex: none;
  gap: 12px;
  align-items: center;
}

.home-task-action {
  flex: none;
  height: 36px;
  padding: 0 14px;
  margin: 0;
  font-size: 13px;
  border-radius: 8px;
}

.home-task-action + .home-task-action {
  margin-left: 0;
}

.home-panel-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.home-message-item {
  display: flex;
  gap: 12px;
  align-items: center;
  width: 100%;
  padding: 16px 0;
  text-align: left;
  cursor: pointer;
  background: transparent;
  border: 0;
  border-bottom: 1px solid #edf1f8;
}

.home-message-item:last-child {
  padding-bottom: 2px;
  border-bottom: 0;
}

.home-message-type {
  flex: none;
  padding: 5px 13px;
  font-size: 12px;
  color: #326cff;
  background: #edf3ff;
  border-radius: 20px;
}

.home-message-type.announcement {
  color: #22995b;
  background: #e8f7ee;
}

.home-message-item strong {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 14px;
  font-weight: 500;
  color: #2b2854;
  white-space: nowrap;
}

.home-message-item strong.unread {
  font-weight: 650;
}

.home-message-item time {
  flex: none;
  font-size: 12px;
  color: #7c83a3;
}

.home-panel-empty {
  display: grid;
  justify-items: center;
  padding: 38px 8px;
  font-size: 13px;
  color: #8a90ab;
}

.home-panel-empty > svg {
  font-size: 32px;
  color: var(--el-color-primary-light-5);
}

.home-panel-empty p {
  margin: 10px 0 0;
}

.home-priority-panel .home-panel-empty {
  align-content: center;
  min-height: 270px;
}

.home-business-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 6px;
  margin-top: 10px;
}

.home-business-grid button {
  display: grid;
  gap: 6px;
  justify-items: center;
  padding: 12px 6px;
  color: #100a43;
  cursor: pointer;
  background: var(--app-button-primary-soft);
  border: 0;
  border-radius: 7px;
}

.home-business-grid button:hover {
  background: var(--app-button-primary-hover-soft);
}

.home-business-grid button > svg {
  font-size: 30px;
  color: var(--el-color-primary);
}

.home-business-grid small {
  font-size: 12px;
  color: #7c83a3;
}

.home-favorites-link {
  margin-top: 12px;
}

.home-panel button:focus-visible {
  outline: 2px solid var(--el-color-primary);
  outline-offset: 3px;
}

@media (width <= 1050px) {
  .home-overview {
    grid-template-columns: minmax(0, 1.35fr) minmax(0, 1fr);
  }

  .home-task-icon {
    width: 44px;
    height: 44px;
    font-size: 25px;
  }
}

@media (width <= 780px) {
  .home-overview {
    grid-template-columns: minmax(0, 1fr);
  }

  .home-column {
    grid-area: auto / 1;
    grid-template-rows: none;
  }

  .home-priority-item {
    flex-wrap: wrap;
    gap: 10px;
  }

  .home-task-action {
    margin-left: auto;
  }

  .home-message-item {
    flex-wrap: wrap;
    gap: 8px;
  }

  .home-message-item strong {
    flex-basis: 60%;
  }
}

.overview-split {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 18px;
}

.overview-split .overview-heading {
  gap: 8px;
  align-items: flex-start;
}

.overview-split .overview-heading-actions {
  flex-wrap: wrap;
  justify-content: flex-end;
}

.overview-split .overview-feed-item {
  grid-template-columns: minmax(0, 1fr);
  gap: 4px;
}

.overview-teal {
  color: #1f8a70;
  background: #e7f6f2;
}

.overview-feed {
  display: grid;
}

.overview-feed-item {
  display: grid;
  grid-template-columns: minmax(0, 1.4fr) minmax(0, 1fr) auto;
  gap: 16px;
  align-items: center;
  width: 100%;
  padding: 12px 2px;
  text-align: left;
  cursor: pointer;
  background: transparent;
  border: 0;
  border-top: 1px solid #eef2f6;
}

.overview-feed-item strong,
.overview-feed-item span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.overview-feed-item strong {
  font-size: 14px;
  color: #274563;
}

.overview-feed-item span,
.overview-feed-item time {
  font-size: 12px;
  color: #8695a7;
}

.overview-feed-item.unread strong::before {
  display: inline-block;
  width: 6px;
  height: 6px;
  margin-right: 6px;
  vertical-align: middle;
  content: "";
  background: #e25b5b;
  border-radius: 50%;
}

.overview-empty {
  padding: 28px 0 12px;
  margin: 0;
  font-size: 13px;
  color: #9aa9ba;
  text-align: center;
}

.overview-panel {
  padding: 25px 30px 28px;
  background: #fff;
  border: 1px solid #e1e9f2;
  border-radius: 18px;
  box-shadow: 0 8px 24px rgb(35 75 116 / 5%);
}

.overview-heading,
.overview-title,
.overview-heading-actions,
.overview-todo-top,
.overview-todo-footer {
  display: flex;
  align-items: center;
}

.overview-heading {
  justify-content: space-between;
  margin-bottom: 20px;
}

.overview-title {
  gap: 10px;
}

.overview-title h1 {
  margin: 0;
  font-size: 20px;
  color: var(--navy);
}

.overview-heading p {
  margin: 7px 0 0 44px;
  font-size: 12px;
  color: #8191a5;
}

.overview-heading-icon {
  display: grid;
  place-items: center;
  width: 35px;
  height: 35px;
  font-size: 19px;
  border-radius: 11px;
}

.overview-blue {
  color: #2474cd;
  background: #eaf4ff;
}

.overview-amber {
  color: #ed9b1d;
  background: #fff4e2;
}

.overview-heading-actions {
  gap: 17px;
}

.overview-total {
  padding: 8px 12px;
  font-size: 12px;
  color: #4e886f;
  background: #eff9f3;
  border-radius: 20px;
}

.overview-total b {
  margin: 0 3px;
  font-size: 16px;
  color: #258e6d;
}

.overview-heading-actions button,
.overview-heading > button {
  display: inline-flex;
  gap: 4px;
  align-items: center;
  padding: 6px 0;
  font: inherit;
  font-size: 12px;
  color: #2e72b7;
  cursor: pointer;
  background: transparent;
  border: 0;
}

.overview-heading-actions button:hover,
.overview-heading-actions button:focus-visible,
.overview-heading > button:hover,
.overview-heading > button:focus-visible {
  color: #1d5b9d;
}

.overview-todo-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
}

.overview-todo-card {
  position: relative;
  display: block;
  min-width: 0;
  min-height: 168px;
  padding: 18px 18px 14px;
  overflow: hidden;
  text-align: left;
  cursor: pointer;
  background: #fff;
  border: 1px solid #e3eaf2;
  border-radius: 13px;
  transition:
    transform 0.2s ease,
    box-shadow 0.2s ease,
    border-color 0.2s ease;
}

.overview-todo-card::before {
  position: absolute;
  top: 0;
  right: 0;
  left: 0;
  height: 4px;
  content: "";
  background: var(--overview-color);
}

.overview-todo-card:hover,
.overview-todo-card:focus-visible {
  border-color: color-mix(in srgb, var(--overview-color) 40%, #e3eaf2);
  box-shadow: 0 10px 22px rgb(36 83 132 / 10%);
  transform: translateY(-2px);
}

.overview-todo-top {
  justify-content: space-between;
}

.overview-todo-icon {
  display: grid;
  place-items: center;
  width: 35px;
  height: 35px;
  font-size: 18px;
  color: var(--overview-color);
  background: var(--overview-soft);
  border-radius: 10px;
}

.overview-todo-top strong {
  font-size: 28px;
  line-height: 1;
  color: var(--overview-color);
}

.overview-todo-top small {
  margin-left: 3px;
  font-size: 11px;
  font-weight: 500;
}

.overview-todo-card h2 {
  margin: 13px 0 5px;
  font-size: 15px;
  color: #264362;
}

.overview-todo-card p {
  min-height: 34px;
  margin: 0;
  font-size: 11px;
  line-height: 1.55;
  color: #8795a7;
}

.overview-todo-footer {
  justify-content: space-between;
  padding-top: 10px;
  margin-top: 11px;
  font-size: 11px;
  color: #95a3b3;
  border-top: 1px dashed #e2e8ef;
}

.overview-todo-footer span:last-child {
  display: inline-flex;
  gap: 3px;
  align-items: center;
  color: #9aa8b8;
}

.overview-todo-card.overview-amber {
  --overview-color: #df921e;
  --overview-soft: #fff4df;
}

.overview-todo-card.overview-blue {
  --overview-color: #258fd0;
  --overview-soft: #e8f7ff;
}

.overview-todo-card.overview-rose {
  --overview-color: #df5272;
  --overview-soft: #fff0f3;
}

.overview-todo-card.overview-violet {
  --overview-color: #7257ca;
  --overview-soft: #f1edff;
}

.overview-favorite-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
}

.overview-favorite-card {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  gap: 12px;
  align-items: center;
  min-width: 0;
  min-height: 82px;
  padding: 14px;
  text-align: left;
  cursor: pointer;
  background: #fbfdff;
  border: 1px solid #e2eaf3;
  border-radius: 11px;
  transition:
    transform 0.2s ease,
    box-shadow 0.2s ease;
}

.overview-favorite-card:hover,
.overview-favorite-card:focus-visible {
  box-shadow: 0 9px 18px rgb(36 83 132 / 9%);
  transform: translateY(-2px);
}

.overview-favorite-icon {
  display: grid;
  place-items: center;
  width: 40px;
  height: 40px;
  font-size: 20px;
  border-radius: 12px;
}

.overview-favorite-copy {
  display: grid;
  gap: 4px;
  min-width: 0;
}

.overview-favorite-copy strong,
.overview-favorite-copy small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.overview-favorite-copy strong {
  font-size: 14px;
  color: #274563;
}

.overview-favorite-copy small {
  font-size: 11px;
  color: #8695a7;
}

.overview-favorite-card > svg {
  color: #9aabba;
}

.detail-heading {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  padding: 0 2px 16px;
  border-bottom: 1px solid #dfe7f0;
}

.back-button {
  display: inline-flex;
  gap: 4px;
  align-items: center;
  padding: 0;
  margin-bottom: 10px;
  font: inherit;
  font-size: 12px;
  color: var(--app-button-primary-ink);
  cursor: pointer;
  background: transparent;
  border: 0;
}

.detail-heading h1 {
  margin: 0;
  font-size: 26px;
  color: var(--navy);
}

.detail-heading p {
  margin: 5px 0 0;
  font-size: 12px;
  color: #8493a5;
}

.detail-summary {
  display: flex;
  gap: 8px;
}

.detail-summary span {
  display: inline-flex;
  gap: 6px;
  align-items: center;
  padding: 9px 12px;
  font-size: 11px;
  color: #6f8297;
  background: #fff;
  border: 1px solid #dfe7f0;
  border-radius: 10px;
}

.detail-summary b {
  font-size: 16px;
  color: #285985;
}

.workbench-intro {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 150px;
  padding: 28px 34px;
  overflow: hidden;
  color: #fff;
  background:
    radial-gradient(circle at 86% 20%, rgb(157 208 255 / 42%), transparent 24%),
    linear-gradient(115deg, #163a64, #2367aa 60%, #3d8bd4);
  border-radius: 20px;
  box-shadow: 0 16px 36px rgb(27 79 135 / 18%);
}

.workbench-intro p {
  margin: 0 0 8px;
  font-size: 11px;
  font-weight: 700;
  color: rgb(224 241 255 / 84%);
  letter-spacing: 0.16em;
}

.workbench-intro h1 {
  margin: 0;
  font-size: clamp(24px, 2.4vw, 32px);
}

.workbench-intro > div > span {
  display: block;
  margin-top: 9px;
  font-size: 13px;
  color: rgb(235 246 255 / 86%);
}

.intro-summary {
  display: flex;
  gap: 12px;
}

.intro-summary span {
  min-width: 96px;
  padding: 15px 18px;
  text-align: center;
  background: rgb(255 255 255 / 12%);
  border: 1px solid rgb(255 255 255 / 20%);
  border-radius: 14px;
  backdrop-filter: blur(8px);
}

.intro-summary b {
  display: block;
  margin-bottom: 3px;
  font-size: 24px;
}

.workspace-card {
  margin-top: 20px;
  overflow: hidden;
  background: var(--el-bg-color);
  border: 1px solid rgb(33 76 123 / 8%);
  border-radius: 20px;
  box-shadow: 0 10px 32px rgb(35 75 116 / 7%);
}

.workspace-tabs {
  display: flex;
  gap: 4px;
  padding: 0 28px;
  overflow-x: auto;
  border-bottom: 1px solid #e7edf4;
}

.workspace-tabs button {
  position: relative;
  display: flex;
  flex: none;
  gap: 8px;
  align-items: center;
  min-height: 56px;
  padding: 0 16px;
  font-size: 14px;
  line-height: 20px;
  color: #74849a;
  cursor: pointer;
  background: transparent;
  border: 0;
  border-radius: 8px 8px 0 0;
  transition: color 0.2s;
}

.workspace-tabs button > svg {
  flex: none;
  font-size: 16px;
}

.workspace-tabs button:hover {
  color: var(--app-button-primary-ink);
}

.workspace-tabs button:focus-visible {
  outline: 2px solid var(--el-color-primary);
  outline-offset: -4px;
}

.workspace-tabs button::after {
  position: absolute;
  right: 15px;
  bottom: 0;
  left: 15px;
  height: 3px;
  content: "";
  background: transparent;
  border-radius: 3px 3px 0 0;
}

.workspace-tabs button.active {
  font-weight: 650;
  color: var(--app-button-primary-ink);
}

.workspace-tabs button.active::after {
  background: var(--blue);
}

.workspace-tabs em {
  display: inline-flex;
  flex: none;
  align-items: center;
  justify-content: center;
  min-width: 20px;
  height: 20px;
  padding: 0 6px;
  font-size: 11px;
  font-style: normal;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  line-height: 1;
  color: var(--el-color-white);
  text-align: center;
  background: var(--el-color-danger);
  border-radius: 10px;
}

.todo-section,
.favorite-section {
  padding: 24px 28px 30px;
}

.toolbar,
.favorite-heading {
  display: flex;
  gap: 18px;
  align-items: center;
  justify-content: space-between;
}

.category-filter {
  display: flex;
  gap: 7px;
  overflow-x: auto;
}

.category-filter button {
  flex: none;
  padding: 7px 12px;
  font-size: 12px;
  color: #687c93;
  cursor: pointer;
  background: #f4f7fa;
  border: 1px solid transparent;
  border-radius: 9px;
}

.category-filter button.active {
  color: var(--app-button-primary-ink);
  background: var(--app-button-primary-soft);
  border-color: var(--app-button-primary-border);
}

.todo-search {
  width: 260px;
}

.todo-list {
  display: grid;
  gap: 12px;
  margin-top: 20px;
}

.todo-item {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  gap: 16px;
  align-items: center;
  padding: 18px 19px;
  background: linear-gradient(145deg, #fff, #fbfcfe);
  border: 1px solid #e7edf4;
  border-radius: 14px;
  transition:
    border-color 0.2s ease,
    box-shadow 0.2s ease;
}

.todo-item:hover {
  border-color: #cbdff3;
  box-shadow: 0 8px 22px rgb(35 89 145 / 8%);
}

.todo-item-icon {
  display: grid;
  place-items: center;
  width: 43px;
  height: 43px;
  font-size: 21px;
  color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
  border-radius: 13px;
}

.priority-高 {
  color: #d95668;
  background: #fff0f2;
}

.priority-中 {
  color: #d78824;
  background: #fff5e7;
}

.todo-copy {
  min-width: 0;
}

.todo-title-row {
  display: flex;
  gap: 9px;
  align-items: center;
}

.todo-title-row h2,
.favorite-heading h2 {
  margin: 0;
  font-size: 15px;
  color: #234563;
}

.todo-copy p,
.favorite-heading p {
  margin: 6px 0 0;
  font-size: 12px;
  line-height: 1.5;
  color: #8391a4;
}

.home-task-copy p.task-facts,
.todo-copy p.task-facts {
  font-size: 14px;
  color: #475569;
  overflow-wrap: anywhere;
  white-space: pre-line;
}

.status-tag {
  flex: none;
  padding: 3px 7px;
  font-size: 10px;
  color: #58748f;
  background: #eff3f7;
  border-radius: 8px;
}

.status-即将到期 {
  color: #cb5966;
  background: #fff0f2;
}

.status-unread {
  color: var(--el-color-danger-dark-2);
  background: var(--el-color-danger-light-9);
}

.status-待复核 {
  color: #9a702b;
  background: #fff6e6;
}

.todo-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 18px;
  margin-top: 9px;
  font-size: 11px;
  color: #97a4b5;
}

.todo-meta span {
  display: inline-flex;
  gap: 4px;
  align-items: center;
}

.favorite-heading {
  align-items: flex-start;
}

.favorite-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
  margin-top: 22px;
}

.favorite-card {
  position: relative;
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  gap: 13px;
  align-items: center;
  min-height: 104px;
  padding: 17px;
  text-align: left;
  cursor: pointer;
  background: linear-gradient(145deg, #fff, #f9fbfd);
  border: 1px solid #e8eef5;
  border-radius: 14px;
  transition:
    transform 0.2s ease,
    box-shadow 0.2s ease;
}

.favorite-card:hover {
  box-shadow: 0 10px 24px rgb(38 87 138 / 10%);
  transform: translateY(-2px);
}

.favorite-icon,
.manager-icon {
  display: grid;
  flex: none;
  place-items: center;
  width: 43px;
  height: 43px;
  font-size: 21px;
  border-radius: 13px;
}

.favorite-copy {
  display: grid;
  gap: 5px;
  min-width: 0;
}

.favorite-copy strong {
  color: #264663;
}

.favorite-copy small {
  overflow: hidden;
  text-overflow: ellipsis;
  color: #8493a6;
  white-space: nowrap;
}

.favorite-type {
  position: absolute;
  right: 14px;
  bottom: 10px;
  font-size: 10px;
  color: #99a6b6;
}

.favorite-arrow {
  color: var(--el-color-primary);
}

.favorite-empty {
  display: grid;
  grid-column: 1 / -1;
  gap: 8px;
  place-items: center;
  min-height: 160px;
  color: #91a1b3;
  background: #f8fafc;
  border: 1px dashed #d7e1ec;
  border-radius: 14px;
}

.favorite-empty svg {
  font-size: 28px;
}

.favorite-empty.compact {
  display: flex;
  justify-content: center;
  min-height: 82px;
}

.favorite-empty.compact svg {
  font-size: 20px;
}

.tone-blue,
.tone-violet,
.tone-teal,
.tone-orange {
  color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}

:global(.el-dialog.favorite-manager-dialog) {
  display: flex;
  flex-direction: column;
  height: min(720px, calc(100dvh - 32px));
  margin: auto;
  overflow: hidden;
  border-radius: 14px;
}

:global(.favorite-manager-dialog .el-dialog__header),
:global(.favorite-manager-dialog .el-dialog__footer) {
  flex: none;
}

:global(.favorite-manager-dialog .el-dialog__body) {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}

:global(.favorite-manager-dialog .el-dialog__footer) {
  padding-top: 16px;
  border-top: 1px solid var(--el-border-color-lighter);
}

.manager-tip {
  flex: none;
  margin: 0 0 12px;
  color: #7b8da3;
}

.manager-selected {
  flex: none;
  padding: 12px;
  margin-bottom: 16px;
  background: var(--el-fill-color-light);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 12px;
}

.manager-subheading {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
  color: #38536f;
}

.manager-subheading span {
  font-size: 12px;
  color: #8a99aa;
}

.manager-candidate-toolbar {
  display: flex;
  flex: none;
  gap: 16px;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.manager-candidate-heading {
  display: grid;
  gap: 4px;
  margin-bottom: 0;
}

.manager-search {
  width: 280px;
}

.manager-candidates {
  flex: 1;
  min-height: 0;
  padding: 2px 4px 12px 2px;
  overflow: auto;
  scrollbar-gutter: stable;
  overscroll-behavior: contain;
}

.manager-candidates:focus-visible {
  outline: 2px solid var(--el-color-primary);
  outline-offset: -2px;
}

.manager-icon {
  width: 32px;
  height: 32px;
  font-size: 18px;
  border-radius: 9px;
}

.manager-sort-list {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

.manager-sort-item {
  display: grid;
  grid-template-columns: auto auto minmax(0, 1fr) auto;
  gap: 6px;
  align-items: center;
  padding: 6px 8px;
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 10px;
}

.manager-drag-handle {
  color: #92a2b4;
  touch-action: none;
  cursor: grab;
}

.manager-drag-handle:active {
  cursor: grabbing;
}

.manager-sort-copy {
  display: grid;
  gap: 2px;
  min-width: 0;
}

.manager-sort-copy strong {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.manager-remove {
  width: 24px;
  height: 24px;
  color: var(--el-text-color-secondary);
}

.manager-sort-ghost {
  opacity: 0.45;
}

.manager-selected-empty {
  padding: 12px;
  color: #98a6b6;
  text-align: center;
  border: 1px dashed #d7e1ec;
  border-radius: 10px;
}

.manager-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

.manager-option {
  width: 100%;
  min-width: 0;
  height: auto;
  padding: 10px;
  margin: 0;
  background: var(--el-fill-color-extra-light);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 11px;
  transition:
    border-color 0.2s,
    background-color 0.2s;
}

.manager-option:hover,
.manager-option:focus-within {
  border-color: var(--el-color-primary-light-5);
}

.manager-option.is-checked {
  background: var(--el-color-primary-light-9);
  border-color: var(--el-color-primary);
}

.manager-option :deep(.el-checkbox__label) {
  display: flex;
  gap: 9px;
  align-items: center;
  min-width: 0;
  line-height: 1.5;
}

.manager-option :deep(.el-checkbox__label > span:last-child) {
  display: grid;
  gap: 2px;
  min-width: 0;
}

.manager-option :deep(.el-checkbox__label > span:last-child strong),
.manager-option :deep(.el-checkbox__label > span:last-child small) {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.manager-option small {
  font-size: 11px;
  color: #8795a8;
}

.empty-state {
  display: grid;
  place-items: center;
  min-height: 260px;
  color: #8b99aa;
}

.empty-state > svg {
  margin-bottom: 10px;
  font-size: 42px;
  color: var(--el-color-primary-light-5);
}

.empty-state span {
  margin-top: 5px;
  font-size: 12px;
}

@media (width <= 900px) {
  .manager-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .overview-todo-grid,
  .overview-favorite-grid,
  .favorite-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .overview-split {
    grid-template-columns: 1fr;
  }

  .workbench-intro {
    align-items: flex-start;
  }
}

@media (width <= 680px) {
  .manager-candidate-toolbar {
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    gap: 10px;
  }

  .manager-search {
    width: 100%;
  }

  .manager-sort-list {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 6px;
  }

  .manager-sort-item {
    grid-template-columns: auto minmax(0, 1fr) auto;
    padding: 4px;
  }

  .manager-sort-item .manager-icon {
    display: none;
  }

  .manager-selected {
    padding: 8px;
    margin-bottom: 10px;
  }

  .overview-panel {
    padding: 18px 16px 20px;
    border-radius: 14px;
  }

  .overview-heading {
    align-items: flex-start;
  }

  .overview-heading-actions {
    gap: 8px;
  }

  .overview-total {
    display: none;
  }

  .overview-todo-grid,
  .overview-favorite-grid {
    grid-template-columns: 1fr;
  }

  .overview-feed-item {
    grid-template-columns: minmax(0, 1fr);
    gap: 4px;
  }

  .detail-heading {
    display: block;
  }

  .detail-summary {
    margin-top: 14px;
  }

  .workbench-intro {
    display: block;
    padding: 23px 20px;
  }

  .intro-summary {
    margin-top: 20px;
  }

  .workspace-tabs,
  .todo-section,
  .favorite-section {
    padding-right: 16px;
    padding-left: 16px;
  }

  .toolbar {
    display: grid;
  }

  .todo-search {
    width: 100%;
  }

  .todo-item {
    grid-template-columns: auto minmax(0, 1fr);
  }

  .todo-item > .el-button {
    grid-column: 2;
    justify-self: start;
  }

  .todo-meta {
    flex-wrap: wrap;
    gap: 6px 12px;
  }

  .favorite-grid {
    grid-template-columns: 1fr;
  }
}

@media (width <= 520px) {
  .manager-grid {
    grid-template-columns: 1fr;
  }
}

@media (height <= 560px) {
  :global(.favorite-manager-dialog .el-dialog__header) {
    padding-bottom: 8px;
  }

  :global(.favorite-manager-dialog .el-dialog__footer) {
    padding-top: 8px;
  }

  .manager-tip {
    display: none;
  }

  .manager-selected {
    padding: 8px;
    margin-bottom: 8px;
  }

  .manager-sort-list {
    display: flex;
    padding-bottom: 4px;
    overflow-x: auto;
  }

  .manager-sort-item {
    flex: 0 0 140px;
    grid-template-columns: auto minmax(0, 1fr) auto;
    padding: 4px;
  }

  .manager-sort-item .manager-icon {
    display: none;
  }

  .manager-subheading {
    margin-bottom: 6px;
  }

  .manager-candidate-heading {
    margin-bottom: 0;
  }

  .manager-candidate-toolbar {
    margin-bottom: 8px;
  }
}
</style>
