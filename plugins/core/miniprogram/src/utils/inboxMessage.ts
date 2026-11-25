import { pages } from "@/pages.json";
import type { InboxMessage, InboxListStore } from "@/store/inbox";

export async function openInboxMessage(
  item: InboxMessage,
  inboxStore: InboxListStore,
) {
  if (item.individualRead) {
    uni.navigateTo({ url: `/pages/notice-detail/index?recipient_id=${encodeURIComponent(item.rawId)}` });
    return;
  }
  if (!(await inboxStore.markRead(item))) return;

  if (item.source === "announcement" && item.target) {
    uni.navigateTo({ url: item.target });
    return;
  }

  if (item.source === "todo" && item.target) {
    uni.navigateTo({ url: item.target });
    return;
  }

  if (item.source === "alert") {
    if (item.target) {
      uni.navigateTo({ url: item.target });
      return;
    }
    uni.showModal({
      title: item.title,
      content: item.content || "请在管理端处理该预警",
      showCancel: false,
      confirmText: "知道了",
    });
    return;
  }

  if (item.requiresConfirmation && !item.confirmed) {
    uni.showModal({
      title: item.title,
      content: item.content || "暂无正文",
      confirmText: "我已知晓",
      cancelText: "关闭",
      success: (result) => {
        if (result.confirm) void inboxStore.confirm(item);
      },
    });
    return;
  }

  const target = item.target;
  const available =
    !!target && pages.some((page) => `/${page.path}` === target.split("?")[0]);
  uni.showModal({
    title: item.title,
    content: item.content || "暂无正文",
    showCancel: available,
    confirmText: available ? "查看详情" : "知道了",
    success: (result) => {
      if (!result.confirm || !available || !target) return;
      const base = target.split("?")[0]!;
      if (__MINIAPP_TAB_PAGES__.includes(base)) uni.switchTab({ url: base });
      else uni.navigateTo({ url: target });
    },
  });
}
