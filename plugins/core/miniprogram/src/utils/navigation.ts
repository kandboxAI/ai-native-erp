export interface NavigationMetrics {
  statusBarHeight: number;
  navigationBarHeight: number;
  totalHeight: number;
  capsuleSafeRight: number;
}

let cachedMetrics: NavigationMetrics | null = null;

export function getNavigationMetrics(): NavigationMetrics {
  if (cachedMetrics) return cachedMetrics;
  let statusBarHeight = 0;
  let navigationBarHeight = 44;
  let capsuleSafeRight = 16;

  // #ifdef MP-WEIXIN
  try {
    const api = uni as unknown as {
      getWindowInfo?: () => { statusBarHeight?: number; windowWidth?: number };
      getSystemInfoSync: () => {
        statusBarHeight?: number;
        windowWidth?: number;
      };
      getMenuButtonBoundingClientRect?: () => {
        top: number;
        bottom: number;
        left: number;
        right: number;
        height: number;
      };
    };
    const windowInfo = api.getWindowInfo?.() || api.getSystemInfoSync();
    const menu = api.getMenuButtonBoundingClientRect?.();
    statusBarHeight = windowInfo.statusBarHeight || 20;
    if (menu?.height) {
      const verticalGap = Math.max(4, menu.top - statusBarHeight);
      navigationBarHeight = menu.height + verticalGap * 2;
      capsuleSafeRight = Math.max(
        96,
        (windowInfo.windowWidth || menu.right) - menu.left + 10
      );
    }
  } catch {
    statusBarHeight = 20;
    navigationBarHeight = 44;
    capsuleSafeRight = 104;
  }
  // #endif

  cachedMetrics = {
    statusBarHeight,
    navigationBarHeight,
    totalHeight: statusBarHeight + navigationBarHeight,
    capsuleSafeRight
  };
  return cachedMetrics;
}
