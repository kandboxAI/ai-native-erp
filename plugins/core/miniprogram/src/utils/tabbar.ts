export function syncTodoTabBarBadge(count: number) {
  // #ifdef MP-WEIXIN
  const index = __MINIAPP_TAB_PAGES__.indexOf("/pages/messages/index");
  if (index < 0) return;
  if (count > 0) {
    uni.setTabBarBadge({
      index,
      text: count > 99 ? "99+" : String(count),
      fail: () => undefined
    });
  } else {
    uni.removeTabBarBadge({ index, fail: () => undefined });
  }
  // #endif
}
