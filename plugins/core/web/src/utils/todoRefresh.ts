import { onBeforeUnmount, onMounted, watch } from "vue";
import { useRoute } from "vue-router";
import { useUserStoreHook } from "@/store/modules/user";

const eventName = "erp:todos-changed";

export function notifyTodosChanged() {
  window.dispatchEvent(new Event(eventName));
}

/** 进入或切换页面、切换身份和业务流转时刷新；切换窗口不刷新。 */
export function useTodoRefresh(refresh: () => void) {
  const route = useRoute();
  const principal = useUserStoreHook();
  const update = () => {
    if (document.visibilityState !== "hidden") refresh();
  };
  onMounted(() => {
    window.addEventListener(eventName, update);
    update();
  });
  watch(
    () => [route.fullPath, principal.username, principal.permissions],
    update,
    { deep: true }
  );
  onBeforeUnmount(() => {
    window.removeEventListener(eventName, update);
  });
}
