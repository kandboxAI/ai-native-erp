<script setup lang="ts">
import { computed, ref, nextTick } from "vue";
import { onHide, onShow, onUnload } from "@dcloudio/uni-app";
import AppTabBar from "@/components/AppTabBar.vue";
import AssistantMarkdown from "@/components/AssistantMarkdown.vue";
import AssistantKnowledgePreview from "@/components/AssistantKnowledgePreview.vue";
// #ifdef MP-WEIXIN
import CustomNavbar from "@/components/CustomNavbar.vue";
// #endif
import { appStore, bootstrapStore } from "@/store/app";
import { bootstrapWorkbench, workbenchStore } from "@/store/workbench";
import {
  createAssistantSession,
  sendAssistantMessage,
  streamAssistantRun,
  listAssistantSessions,
  getAssistantHistory,
  deleteAssistantSession,
  listAssistantWriteApprovals,
  decideAssistantWriteApproval,
  type AssistantRun,
  type AssistantSessionItem,
  type AssistantWriteApproval,
} from "@/api/aiAssistant";

interface ChatMessage {
  id: string;
  role: "assistant" | "user";
  text: string;
  time: string;
}
bootstrapStore();
bootstrapWorkbench();
const branding = __PRODUCT_BRANDING__;
const inputText = ref("");
const citationAddress = ref("");
const messages = ref<ChatMessage[]>([]);
const thinking = ref(false);
const writeApproval = ref<AssistantWriteApproval | null>(null);
const approvalBusy = ref(false);
const activeReplyId = ref("");
const sessionId = ref("");
const historyOpen = ref(false);
const historyLoading = ref(false);
const historyError = ref("");
const historyItems = ref<AssistantSessionItem[]>([]);
const historyMore = ref(false);
const historyOffset = ref(0);
const openingSessionId = ref("");
const deletingSessionId = ref("");
const scrollTarget = ref("");
const conversationDate = ref("今天");
const profile = computed(() => appStore.currentProfile.value);
const prompts = [
  "查找可访问的功能入口",
  "说明当前可用的业务应用",
  "查看我的待办任务",
  "查询知识库中的操作说明",
];
const overview = computed(() => ({
  value: workbenchStore.unreadCount.value,
  label: "条未读消息",
  description: "依据当前账号权限查询 ERP 数据和企业知识",
}));
let ownerId = "";
let disposed = false;
let sequence = 0;
let receiving: ReturnType<typeof streamAssistantRun> | undefined;
let approvalTimer: ReturnType<typeof setInterval> | undefined;
let activeRunId = "";
let generation = 0;
let historyRequest = 0;

function scrollToEnd() {
  scrollTarget.value = "";
  nextTick(() => {
    if (!disposed) scrollTarget.value = "chat-end";
  });
}

function append(role: "user" | "assistant", text: string) {
  messages.value.push({
    id: `agent-${Date.now()}-${++sequence}`,
    role,
    text,
    time: new Date().toLocaleTimeString().slice(0, 5),
  });
  scrollToEnd();
  return messages.value[messages.value.length - 1];
}
async function submitQuestion(question?: string) {
  const content = (question || inputText.value).trim();
  if (!content || thinking.value || openingSessionId.value) return;
  inputText.value = "";
  thinking.value = true;
  const currentGeneration = generation;
  append("user", content);
  const reply = append("assistant", "");
  activeReplyId.value = reply?.id || "";
  try {
    if (!sessionId.value) {
      const created = await createAssistantSession();
      if (disposed || currentGeneration !== generation) return;
      sessionId.value = created.session_id;
    }
    if (disposed || currentGeneration !== generation) return;
    const run = await sendAssistantMessage(sessionId.value, content);
    if (disposed || currentGeneration !== generation) return;
    await receiveAnswer(run, reply, currentGeneration);
    if (!disposed && currentGeneration === generation && reply && !reply.text) {
      reply.text = "本轮没有返回文字回答，请重新发送问题。";
    }
  } catch (error) {
    if (!disposed && currentGeneration === generation) {
      const text =
        error instanceof Error ? error.message : "智能体请求失败，请稍后重试";
      if (reply) reply.text = [reply.text, text].filter(Boolean).join("\n\n");
      else append("assistant", text);
      scrollToEnd();
    }
  } finally {
    if (currentGeneration === generation) {
      thinking.value = false;
      activeReplyId.value = "";
      receiving = undefined;
    }
  }
}

async function receiveAnswer(
  run: AssistantRun,
  reply: ChatMessage | undefined,
  epoch: number,
) {
  activeRunId = run.run_id;
  receiving = streamAssistantRun(run.session_id, run.run_id, (answer) => {
    if (disposed || epoch !== generation || !reply) return;
    reply.text = answer;
    scrollToEnd();
  });
  try {
    await receiving.promise;
  } finally {
    if (activeRunId === run.run_id) {
      activeRunId = "";
      writeApproval.value = null;
    }
  }
}

async function pollWriteApproval() {
  if (!thinking.value || !activeRunId || approvalBusy.value || disposed) return;
  const runId = activeRunId;
  const actor = ownerId;
  try {
    const pending = await listAssistantWriteApprovals();
    if (disposed || actor !== ownerId || runId !== activeRunId) return;
    writeApproval.value = pending.find((item) => item.session_id === sessionId.value && item.run_id === runId) || null;
  } catch {
    // The run stream reports authentication and server errors.
  }
}

async function decideWrite(approved: boolean) {
  const current = writeApproval.value;
  if (!current || approvalBusy.value) return;
  approvalBusy.value = true;
  try {
    await decideAssistantWriteApproval(current.approval_id, approved);
    if (writeApproval.value?.approval_id === current.approval_id) writeApproval.value = null;
  } catch (error) {
    uni.showToast({ title: error instanceof Error ? error.message : "确认已过期", icon: "none" });
  } finally {
    approvalBusy.value = false;
  }
}

function newSession() {
  if (thinking.value || openingSessionId.value) return;
  citationAddress.value = "";
  generation++;
  writeApproval.value = null;
  activeRunId = "";
  sessionId.value = "";
  inputText.value = "";
  activeReplyId.value = "";
  conversationDate.value = "今天";
  messages.value = [];
  append(
    "assistant",
    `我是${branding.assistant_name}，可以根据你的权限查询业务数据、检索企业知识，并提供资料来源。请输入问题。`,
  );
}

function formatHistoryDate(value: string | null) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return `${date.getMonth() + 1}月${date.getDate()}日 ${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}`;
}

async function loadHistory(reset = false) {
  if (historyLoading.value && !reset) return;
  const requestId = ++historyRequest;
  const actor = ownerId;
  historyLoading.value = true;
  historyError.value = "";
  if (reset) {
    historyItems.value = [];
    historyOffset.value = 0;
    historyMore.value = false;
  }
  try {
    const page = await listAssistantSessions(historyOffset.value);
    if (disposed || requestId !== historyRequest || actor !== ownerId) return;
    const seen = new Set(historyItems.value.map((row) => row.session_id));
    historyItems.value.push(
      ...page.items.filter((row) => !seen.has(row.session_id)),
    );
    historyOffset.value = page.next_offset;
    historyMore.value = page.has_more;
  } catch (error) {
    if (!disposed && requestId === historyRequest && actor === ownerId)
      historyError.value =
        error instanceof Error ? error.message : "历史会话加载失败";
  } finally {
    if (requestId === historyRequest) historyLoading.value = false;
  }
}

function openHistory() {
  historyOpen.value = true;
  void loadHistory(true);
}

async function openSession(row: AssistantSessionItem) {
  if (thinking.value) {
    uni.showToast({ title: "请等待当前回答完成", icon: "none" });
    return;
  }
  if (openingSessionId.value || deletingSessionId.value) return;
  const epoch = ++generation;
  openingSessionId.value = row.session_id;
  let reply: ChatMessage | undefined;
  try {
    const history = await getAssistantHistory(row.session_id);
    if (disposed || epoch !== generation) return;
    sessionId.value = history.session_id;
    conversationDate.value =
      formatHistoryDate(row.created_at).split(" ")[0] || "历史会话";
    inputText.value = "";
    messages.value = history.messages.map((message) => ({
      id: message.id,
      role: message.role,
      text: message.content,
      time: formatHistoryDate(message.created_at),
    }));
    historyOpen.value = false;
    scrollToEnd();
    openingSessionId.value = "";
    if (history.active_run) {
      thinking.value = true;
      reply =
        messages.value.find(
          (message) => message.id === `${history.active_run!.run_id}:assistant`,
        ) || append("assistant", "");
      activeReplyId.value = reply?.id || "";
      await receiveAnswer(history.active_run, reply, epoch);
      if (!disposed && epoch === generation && reply && !reply.text)
        reply.text = "本轮没有返回文字回答，请重新发送问题。";
    }
  } catch (error) {
    if (!disposed && epoch === generation) {
      const text = error instanceof Error ? error.message : "会话打开失败";
      if (reply) reply.text = [reply.text, text].filter(Boolean).join("\n\n");
      else uni.showToast({ title: text, icon: "none" });
    }
  } finally {
    if (epoch === generation) {
      openingSessionId.value = "";
      thinking.value = false;
      activeReplyId.value = "";
      receiving = undefined;
    }
  }
}

async function removeSession(row: AssistantSessionItem) {
  if (deletingSessionId.value || openingSessionId.value) return;
  if (thinking.value && sessionId.value === row.session_id) {
    uni.showToast({ title: "请等待该会话回答完成", icon: "none" });
    return;
  }
  const actor = ownerId;
  const confirmed = await new Promise<boolean>((resolve) =>
    uni.showModal({
      title: "删除会话",
      content: `确定删除“${row.title}”吗？`,
      success: (result) => resolve(result.confirm),
      fail: () => resolve(false),
    }),
  );
  if (!confirmed || disposed || actor !== ownerId) return;
  deletingSessionId.value = row.session_id;
  try {
    await deleteAssistantSession(row.session_id);
    if (disposed || actor !== ownerId) return;
    if (sessionId.value === row.session_id) newSession();
    await loadHistory(true);
  } catch (error) {
    if (!disposed && actor === ownerId)
      uni.showToast({
        title: error instanceof Error ? error.message : "会话删除失败",
        icon: "none",
      });
  } finally {
    if (actor === ownerId) deletingSessionId.value = "";
  }
}
onShow(() => {
  if (!appStore.state.loggedIn) {
    uni.reLaunch({ url: "/pages/login/index" });
    return;
  }
  const currentOwner = appStore.state.account?.userId || "";
  if (ownerId !== currentOwner) {
    generation++;
    receiving?.abort();
    receiving = undefined;
    thinking.value = false;
    activeReplyId.value = "";
    historyRequest++;
    historyOpen.value = false;
    historyLoading.value = false;
    historyItems.value = [];
    historyError.value = "";
    historyOffset.value = 0;
    historyMore.value = false;
    openingSessionId.value = "";
    deletingSessionId.value = "";
    ownerId = currentOwner;
    newSession();
  } else if (!messages.value.length) newSession();
  if (!approvalTimer) approvalTimer = setInterval(() => void pollWriteApproval(), 1000);
  void pollWriteApproval();
});
onHide(() => {
  if (approvalTimer) clearInterval(approvalTimer);
  approvalTimer = undefined;
  writeApproval.value = null;
});
onUnload(() => {
  disposed = true;
  generation++;
  historyRequest++;
  receiving?.abort();
  if (approvalTimer) clearInterval(approvalTimer);
});
</script>

<template>
  <view class="xiaohang-page">
    <view class="agent-header">
      <view class="header-orbit header-orbit--one" />
      <view class="header-orbit header-orbit--two" />
      <!-- #ifdef MP-WEIXIN -->
      <CustomNavbar light>
        <view class="nav-brand">
          <view class="mini-agent">航</view>
          <view
            ><text>{{ branding.assistant_name }}</text
            ><small>AI 业务助手</small></view
          >
        </view>
      </CustomNavbar>
      <!-- #endif -->
      <!-- #ifndef MP-WEIXIN -->
      <view class="h5-navbar">
        <view class="nav-brand">
          <view class="mini-agent">航</view>
          <view
            ><text>{{ branding.assistant_name }}</text
            ><small>AI 业务助手</small></view
          >
        </view>
      </view>
      <!-- #endif -->
      <view class="header-copy">
        <view>
          <text class="header-kicker">你好，{{ profile.name }}</text>
          <text class="header-title">今天想让我帮你做什么？</text>
        </view>
        <view class="chat-actions">
          <view class="chat-action" @tap="openHistory"><text>历史</text></view>
          <view class="chat-action" @tap="newSession"><text>新会话</text></view>
        </view>
      </view>
      <view class="context-card">
        <view class="context-icon">智</view>
        <view class="grow">
          <text class="context-title">{{ profile.roleName }}智能工作台</text>
          <text class="context-desc">{{ overview.description }}</text>
        </view>
        <view class="context-count">
          <text>{{ overview.value }}</text
          ><small>{{ overview.label }}</small>
        </view>
      </view>
    </view>

    <view class="quick-section">
      <view class="quick-heading">
        <text>试着问{{ branding.assistant_name }}</text>
      </view>
      <view class="prompt-row">
        <view
          v-for="(prompt, index) in prompts"
          :key="prompt"
          class="prompt-chip pressable"
          @tap="submitQuestion(prompt)"
        >
          <text class="prompt-icon" :class="`prompt-icon--${index + 1}`">{{
            ["问", "办", "查", "回"][index]
          }}</text>
          <text class="prompt-label">{{ prompt }}</text>
        </view>
      </view>
    </view>

    <scroll-view
      scroll-y
      class="conversation"
      :scroll-into-view="scrollTarget"
      :scroll-with-animation="true"
    >
      <view class="conversation-inner">
        <view class="conversation-date">{{ conversationDate }}</view>
        <view
          v-for="message in messages"
          :id="message.id"
          :key="message.id"
          class="message-row"
          :class="`message-row--${message.role}`"
        >
          <view v-if="message.role === 'assistant'" class="message-avatar"
            >航</view
          >
          <view class="message-content">
            <view v-if="message.text" class="message-bubble">
              <AssistantMarkdown
                v-if="message.role === 'assistant'"
                :content="message.text"
                @cite="citationAddress = $event"
              />
              <text v-else>{{ message.text }}</text>
            </view>
            <view
              v-else-if="thinking && message.id === activeReplyId"
              class="thinking-bubble"
              aria-label="正在查询和生成回答"
              ><view /><view /><view
            /></view>
            <text v-if="message.text" class="message-time">{{
              message.time
            }}</text>
          </view>
        </view>
        <view id="chat-end" class="chat-end" />
      </view>
    </scroll-view>

    <view class="composer">
      <view class="composer-inner">
        <input
          v-model="inputText"
          class="composer-input"
          confirm-type="send"
          :disabled="thinking || Boolean(openingSessionId)"
          placeholder="有什么需要帮忙？"
          placeholder-class="composer-placeholder"
          @confirm="submitQuestion()"
        />
        <view
          class="send-button pressable"
          :class="{
            disabled:
              !inputText.trim() || thinking || Boolean(openingSessionId),
          }"
          @tap="submitQuestion()"
          ><text>↑</text></view
        >
      </view>
    </view>

    <AppTabBar current="xiaohang" :reserve-space="false" />
    <AssistantKnowledgePreview
      v-if="citationAddress"
      :address="citationAddress"
      @close="citationAddress = ''"
    />

    <view v-if="writeApproval" class="write-approval-overlay">
      <view class="write-approval-sheet">
        <text class="write-approval-title">确认业务操作</text>
        <text class="write-approval-hint">请核对接口和参数。确认后仅执行本次操作。</text>
        <scroll-view scroll-y class="write-approval-preview"><text selectable>{{ writeApproval.preview }}</text></scroll-view>
        <view class="write-approval-actions">
          <button :disabled="approvalBusy" @tap="decideWrite(false)">拒绝</button>
          <button class="write-approval-confirm" :disabled="approvalBusy" @tap="decideWrite(true)">确认执行</button>
        </view>
      </view>
    </view>

    <view v-if="historyOpen" class="history-overlay" @tap="historyOpen = false">
      <view class="history-sheet" @tap.stop>
        <view class="history-heading">
          <view
            ><text class="history-title">历史会话</text
            ><text class="history-subtitle">仅显示当前账号的会话</text></view
          >
          <text class="history-close" @tap="historyOpen = false">关闭</text>
        </view>
        <scroll-view scroll-y class="history-list">
          <view
            v-if="historyLoading && !historyItems.length"
            class="history-empty"
            >正在加载历史会话…</view
          >
          <view
            v-else-if="!historyItems.length && !historyError"
            class="history-empty"
            >暂无历史会话，提问后会自动保存</view
          >
          <view
            v-for="row in historyItems"
            :key="row.session_id"
            class="history-row"
            :class="{ 'history-row--active': row.session_id === sessionId }"
            @tap="openSession(row)"
          >
            <view class="history-row-copy">
              <text class="history-row-title">{{ row.title }}</text>
              <text class="history-row-date"
                >{{ formatHistoryDate(row.updated_at)
                }}{{
                  openingSessionId === row.session_id
                    ? " · 正在打开"
                    : row.session_id === sessionId
                      ? " · 当前会话"
                      : ""
                }}</text
              >
            </view>
            <text class="history-delete" @tap.stop="removeSession(row)">{{
              deletingSessionId === row.session_id ? "删除中" : "删除"
            }}</text>
          </view>
          <view
            v-if="historyError"
            class="history-error"
            @tap="loadHistory(!historyItems.length)"
            >{{ historyError }} · 点击重试</view
          >
          <view
            v-else-if="historyMore"
            class="history-more"
            @tap="loadHistory()"
            >{{ historyLoading ? "正在加载…" : "加载更多" }}</view
          >
          <view v-else-if="historyItems.length" class="history-more"
            >已显示全部会话</view
          >
        </scroll-view>
      </view>
    </view>
  </view>
</template>

<style scoped lang="scss">
.write-approval-overlay {
  position: fixed;
  inset: 0;
  z-index: 1200;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 32rpx;
  background: rgba(14, 31, 55, 0.65);
}
.write-approval-sheet {
  width: 100%;
  padding: 32rpx;
  background: #fff;
  border-radius: 24rpx;
}
.write-approval-title { display: block; font-size: 34rpx; font-weight: 700; color: #1f3657; }
.write-approval-hint { display: block; margin: 12rpx 0 24rpx; color: #68758a; font-size: 24rpx; }
.write-approval-preview {
  height: 40vh;
  padding: 20rpx;
  box-sizing: border-box;
  background: #f4f7fb;
  border-radius: 12rpx;
}
.write-approval-preview text { white-space: pre-wrap; overflow-wrap: anywhere; font-family: monospace; font-size: 22rpx; }
.write-approval-actions { display: flex; gap: 20rpx; margin-top: 28rpx; }
.write-approval-actions button { flex: 1; margin: 0; }
.write-approval-confirm { color: #fff; background: #1769e0; }
.chat-actions {
  display: flex;
  gap: 12rpx;
  flex-shrink: 0;
  margin-left: 12rpx;
}
.chat-action {
  padding: 12rpx 16rpx;
  font-size: 22rpx;
  background: rgba(255, 255, 255, 0.16);
  border: 1rpx solid rgba(255, 255, 255, 0.24);
  border-radius: 16rpx;
}
.history-overlay {
  position: fixed;
  inset: 0;
  z-index: 1000;
  display: flex;
  align-items: flex-end;
  background: rgba(14, 31, 55, 0.45);
}
.history-sheet {
  width: 100%;
  height: 72vh;
  padding-bottom: env(safe-area-inset-bottom);
  background: #f7f9fc;
  border-radius: 30rpx 30rpx 0 0;
}
.history-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 32rpx;
  border-bottom: 1rpx solid #e5ebf3;
}
.history-heading > view {
  display: flex;
  flex-direction: column;
  gap: 8rpx;
}
.history-title {
  color: #1f3657;
  font-size: 32rpx;
  font-weight: 700;
}
.history-subtitle {
  color: #8997aa;
  font-size: 22rpx;
}
.history-close {
  padding: 10rpx 0 10rpx 24rpx;
  color: #246bd0;
  font-size: 26rpx;
}
.history-list {
  height: calc(72vh - 140rpx);
}
.history-row {
  display: flex;
  align-items: center;
  margin: 16rpx 24rpx;
  padding: 24rpx;
  border: 1rpx solid #e5ebf3;
  background: #fff;
  border-radius: 20rpx;
}
.history-row--active {
  border-color: #9cbfea;
  background: #eef5ff;
}
.history-row-copy {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 12rpx;
}
.history-row-title {
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
  color: #253d5e;
  font-size: 26rpx;
  font-weight: 600;
}
.history-row-date {
  color: #8997aa;
  font-size: 21rpx;
}
.history-delete {
  flex-shrink: 0;
  padding: 18rpx 0 18rpx 24rpx;
  color: #b06f77;
  font-size: 22rpx;
}
.history-empty,
.history-error,
.history-more {
  padding: 44rpx 32rpx;
  text-align: center;
  font-size: 25rpx;
  color: #8997aa;
}
.history-error {
  color: #bd5963;
}
.xiaohang-page {
  height: 100vh;
  overflow: hidden;
  background: #f2f6fb;
}
.agent-header {
  position: relative;
  height: 370rpx;
  overflow: hidden;
  color: #fff;
  background: linear-gradient(145deg, #0b4ca9, #1769e0 58%, #1489b0);
  border-radius: 0 0 44rpx 44rpx;
}
.header-orbit {
  position: absolute;
  border: 2rpx solid rgba(255, 255, 255, 0.11);
  border-radius: 50%;
}
.header-orbit--one {
  top: -250rpx;
  right: -70rpx;
  width: 520rpx;
  height: 520rpx;
}
.header-orbit--two {
  right: 140rpx;
  bottom: -320rpx;
  width: 470rpx;
  height: 470rpx;
}
.h5-navbar {
  position: relative;
  z-index: 2;
  display: flex;
  height: 102rpx;
  align-items: center;
  justify-content: space-between;
  padding: 0 32rpx;
}
.nav-brand {
  display: flex;
  align-items: center;
  gap: 15rpx;
}
.nav-brand > view:last-child {
  display: flex;
  flex-direction: column;
}
.nav-brand text {
  color: #fff;
  font-size: 28rpx;
  font-weight: 750;
}
.nav-brand small {
  margin-top: 2rpx;
  color: rgba(255, 255, 255, 0.68);
  font-size: 17rpx;
  letter-spacing: 1rpx;
}
.mini-agent {
  display: flex;
  width: 56rpx;
  height: 56rpx;
  align-items: center;
  justify-content: center;
  color: #1769e0;
  background: #fff;
  border-radius: 18rpx;
  font-size: 27rpx;
  font-weight: 800;
}
.demo-pill {
  padding: 7rpx 13rpx;
  color: #e4f6ff;
  background: rgba(255, 255, 255, 0.14);
  border: 1rpx solid rgba(255, 255, 255, 0.2);
  border-radius: 99rpx;
  font-size: 16rpx;
  letter-spacing: 2rpx;
}
.header-copy {
  position: relative;
  z-index: 2;
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  padding: 23rpx 32rpx 0;
}
.header-kicker,
.header-title {
  display: block;
}
.header-kicker {
  font-size: 22rpx;
  opacity: 0.75;
}
.header-title {
  margin-top: 8rpx;
  font-size: 37rpx;
  font-weight: 760;
  letter-spacing: -1rpx;
}
.online-dot {
  display: flex;
  align-items: center;
  gap: 7rpx;
  padding-bottom: 6rpx;
  font-size: 18rpx;
  opacity: 0.8;
}
.online-dot view {
  width: 10rpx;
  height: 10rpx;
  background: #75f0c2;
  border-radius: 50%;
  box-shadow: 0 0 12rpx #75f0c2;
}
.context-card {
  position: absolute;
  right: 28rpx;
  bottom: 26rpx;
  left: 28rpx;
  z-index: 2;
  display: flex;
  align-items: center;
  gap: 17rpx;
  padding: 17rpx 20rpx;
  background: rgba(255, 255, 255, 0.13);
  border: 1rpx solid rgba(255, 255, 255, 0.18);
  border-radius: 22rpx;
  backdrop-filter: blur(10px);
}
.context-icon {
  display: flex;
  width: 53rpx;
  height: 53rpx;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  color: #0e62ca;
  background: #fff;
  border-radius: 16rpx;
  font-size: 21rpx;
  font-weight: 750;
}
.context-title,
.context-desc {
  display: block;
}
.context-title {
  font-size: 23rpx;
  font-weight: 650;
}
.context-desc {
  margin-top: 5rpx;
  font-size: 18rpx;
  opacity: 0.67;
}
.context-count {
  display: flex;
  flex: 0 0 auto;
  flex-direction: column;
  align-items: flex-end;
}
.context-count text {
  font-size: 30rpx;
  font-weight: 760;
}
.context-count small {
  font-size: 17rpx;
  opacity: 0.67;
}
.quick-section {
  padding: 27rpx 0 12rpx;
}
.quick-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 28rpx 15rpx;
}
.quick-heading text {
  font-size: 27rpx;
  font-weight: 700;
}
.quick-heading small {
  color: #929cac;
  font-size: 18rpx;
}
.prompt-row {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14rpx;
  padding: 0 28rpx 19rpx;
}
.prompt-chip {
  display: flex;
  min-width: 0;
  height: 78rpx;
  align-items: center;
  gap: 13rpx;
  padding: 0 17rpx 0 12rpx;
  color: #46566d;
  background: #fff;
  border: 1rpx solid #e6ecf4;
  border-radius: 20rpx;
  box-shadow: 0 7rpx 20rpx rgba(22, 58, 105, 0.045);
}
.prompt-icon {
  display: flex;
  width: 48rpx;
  height: 48rpx;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  color: #1769e0;
  background: #eaf2ff;
  border-radius: 14rpx;
  font-size: 19rpx;
  font-weight: 750;
}
.prompt-icon--2 {
  color: #7453c5;
  background: #f0edff;
}
.prompt-icon--3 {
  color: #138b5a;
  background: #e8f8f1;
}
.prompt-icon--4 {
  color: #c8740c;
  background: #fff2df;
}
.prompt-label {
  min-width: 0;
  overflow: hidden;
  font-size: 22rpx;
  font-weight: 560;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.conversation {
  height: calc(100vh - 868rpx - env(safe-area-inset-bottom));
  min-height: 390rpx;
}
.conversation-inner {
  padding: 6rpx 28rpx 30rpx;
}
.conversation-date {
  margin: 10rpx 0 25rpx;
  color: #9aa4b3;
  font-size: 18rpx;
  text-align: center;
}
.message-row {
  display: flex;
  align-items: flex-start;
  gap: 14rpx;
  margin-bottom: 28rpx;
}
.message-row--user {
  justify-content: flex-end;
}
.message-avatar {
  display: flex;
  width: 53rpx;
  height: 53rpx;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  color: #fff;
  background: linear-gradient(145deg, #2d83ef, #0f58bd);
  border-radius: 17rpx;
  font-size: 22rpx;
  font-weight: 800;
  box-shadow: 0 7rpx 16rpx rgba(23, 105, 224, 0.18);
}
.message-content {
  min-width: 0;
  max-width: calc(100% - 68rpx);
}
.message-row--user .message-content {
  max-width: 82%;
}
.message-bubble {
  padding: 20rpx 23rpx;
  color: #34445a;
  background: #fff;
  border: 1rpx solid rgba(28, 55, 91, 0.06);
  border-radius: 7rpx 23rpx 23rpx 23rpx;
  box-shadow: 0 8rpx 25rpx rgba(22, 58, 105, 0.05);
}
.message-bubble text {
  font-size: 23rpx;
  line-height: 1.7;
}
.message-row--user .message-bubble {
  color: #fff;
  background: linear-gradient(135deg, #2779e6, #145cc5);
  border: 0;
  border-radius: 23rpx 7rpx 23rpx 23rpx;
}
.message-time {
  display: block;
  margin-top: 8rpx;
  color: #a3acb8;
  font-size: 16rpx;
}
.message-row--user .message-time {
  text-align: right;
}
.result-card {
  margin-top: 12rpx;
  padding: 22rpx;
  background: #fff;
  border: 1rpx solid #dce9fb;
  border-left: 6rpx solid #1769e0;
  border-radius: 20rpx;
  box-shadow: 0 8rpx 25rpx rgba(22, 58, 105, 0.05);
}
.result-card.tone-green {
  border-color: #d9f0e6;
  border-left-color: #18a66a;
}
.result-card.tone-orange {
  border-color: #f5e8d3;
  border-left-color: #f0a020;
}
.result-card.tone-purple {
  border-color: #e7e0fa;
  border-left-color: #7957c8;
}
.result-eyebrow,
.result-title,
.result-note {
  display: block;
}
.result-eyebrow {
  color: #1769e0;
  font-size: 18rpx;
  font-weight: 650;
}
.tone-green .result-eyebrow {
  color: #138b59;
}
.tone-orange .result-eyebrow {
  color: #c87810;
}
.tone-purple .result-eyebrow {
  color: #7652c4;
}
.result-title {
  margin-top: 7rpx;
  font-size: 28rpx;
  font-weight: 720;
}
.result-rows {
  margin-top: 16rpx;
  padding: 7rpx 15rpx;
  background: #f6f8fb;
  border-radius: 14rpx;
}
.result-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20rpx;
  padding: 10rpx 0;
  color: #8490a1;
  font-size: 19rpx;
}
.result-row text:last-child {
  max-width: 70%;
  color: #3f4f65;
  text-align: right;
}
.result-row text.warn {
  color: #d3790a;
  font-weight: 650;
}
.result-note {
  margin-top: 14rpx;
  color: #68758a;
  font-size: 19rpx;
  line-height: 1.6;
}
.action-row {
  display: flex;
  flex-wrap: wrap;
  gap: 12rpx;
  margin-top: 13rpx;
}
.agent-action {
  height: 61rpx;
  padding: 0 24rpx;
  margin: 0;
  color: #1769e0;
  background: #eaf2ff;
  border-radius: 17rpx;
  font-size: 21rpx;
  font-weight: 650;
  line-height: 61rpx;
}
.agent-action.primary {
  color: #fff;
  background: linear-gradient(135deg, #2478e7, #1257bc);
  box-shadow: 0 8rpx 18rpx rgba(23, 105, 224, 0.18);
}
.thinking-bubble {
  display: flex;
  gap: 7rpx;
  padding: 22rpx 25rpx;
  background: #fff;
  border-radius: 7rpx 23rpx 23rpx 23rpx;
}
.thinking-bubble view {
  width: 8rpx;
  height: 8rpx;
  background: #8ca2bf;
  border-radius: 50%;
  animation: thinking 1s infinite ease-in-out;
}
.thinking-bubble view:nth-child(2) {
  animation-delay: 0.15s;
}
.thinking-bubble view:nth-child(3) {
  animation-delay: 0.3s;
}
@keyframes thinking {
  0%,
  60%,
  100% {
    opacity: 0.35;
    transform: translateY(0);
  }
  30% {
    opacity: 1;
    transform: translateY(-5rpx);
  }
}
.chat-end {
  height: 1rpx;
}
.composer {
  position: fixed;
  right: 0;
  bottom: calc(132rpx + env(safe-area-inset-bottom));
  left: 0;
  z-index: 70;
  padding: 15rpx 24rpx 10rpx;
  background: rgba(247, 249, 252, 0.97);
  border-top: 1rpx solid #e7ecf3;
  backdrop-filter: blur(14px);
}
.composer-inner {
  display: flex;
  height: 76rpx;
  align-items: center;
  gap: 12rpx;
  padding: 8rpx 9rpx 8rpx 23rpx;
  background: #fff;
  border: 1rpx solid #dee6f0;
  border-radius: 23rpx;
  box-shadow: 0 7rpx 22rpx rgba(22, 58, 105, 0.06);
}
.composer-input {
  height: 58rpx;
  flex: 1;
  color: #25364d;
  font-size: 22rpx;
}
.send-button {
  display: flex;
  width: 57rpx;
  height: 57rpx;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  color: #fff;
  background: #1769e0;
  border-radius: 18rpx;
  font-size: 29rpx;
  font-weight: 750;
}
.send-button.disabled {
  background: #b9c6d8;
  box-shadow: none;
}
:deep(.composer-placeholder) {
  color: #a1aab7;
}
/* #ifdef MP-WEIXIN */
.agent-header {
  height: 408rpx;
}
.conversation {
  height: calc(100vh - 906rpx - env(safe-area-inset-bottom));
}
.header-copy {
  padding-top: 14rpx;
}
/* #endif */
</style>
