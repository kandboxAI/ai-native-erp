import { appStore } from "@/store/app";

export const hasPermission = (permission: string) =>
  Boolean(appStore.state.account?.permissions.includes(permission));

export function confirmAction(
  title: string,
  content: string,
): Promise<boolean> {
  return new Promise((resolve) =>
    uni.showModal({
      title,
      content,
      success: (result) => resolve(result.confirm),
      fail: () => resolve(false),
    }),
  );
}

export function showApiError(error: unknown, fallback = "操作失败") {
  uni.showToast({
    title: error instanceof Error ? error.message : fallback,
    icon: "none",
  });
}
