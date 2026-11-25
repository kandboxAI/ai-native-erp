<script setup lang="ts">
import { onLaunch, onShow, onHide } from "@dcloudio/uni-app";
import { resumePluginAccess, pausePluginAccess } from "@/store/pluginAccess";
import { appStore, bootstrapStore } from "@/store/app";
import { workbenchStore, bootstrapWorkbench } from "@/store/workbench";
import { rememberTodoEntry } from "@/utils/todoEntry";

function ensureAuthenticated() {
  bootstrapStore();
  if (appStore.state.loggedIn && appStore.state.account) {
    void workbenchStore
      .refreshNotifications()
      .then(() => workbenchStore.syncUnreadBadge()).catch(() => undefined);
    return;
  }
  const pages = getCurrentPages();
  const currentRoute = pages[pages.length - 1]?.route || "";
  if (currentRoute && currentRoute !== "pages/login/index") {
    uni.reLaunch({ url: "/pages/login/index" });
  }
}

onLaunch(options => {
  bootstrapStore();
  if (!appStore.state.loggedIn) rememberTodoEntry(options?.path || "", String(options?.query?.id || ""));
  bootstrapWorkbench();
  setTimeout(ensureAuthenticated, 0);
});
onShow((options?: { path?: string; query?: Record<string, string> }) => {
  if (!appStore.state.loggedIn) rememberTodoEntry(options?.path || "", String(options?.query?.id || ""));
  resumePluginAccess();
  ensureAuthenticated();
  if (appStore.state.loggedIn && appStore.state.account) {
    workbenchStore.refreshNotificationUnreadCount().catch(() => undefined);
    workbenchStore.refreshPendingCount().catch(() => undefined);
  }
});
onHide(pausePluginAccess);
</script>

<style lang="scss">
@use "./styles/global.scss";
</style>
