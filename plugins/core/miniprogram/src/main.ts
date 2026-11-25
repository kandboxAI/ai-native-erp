import { createSSRApp } from "vue";
import App from "./App.vue";
import {
  installPluginNavigation,
  refreshPluginAccess,
  enforceCurrentPage,
} from "@/store/pluginAccess";

export function createApp() {
  installPluginNavigation();
  const app = createSSRApp(App);
  app.mixin({
    onShow() {
      void refreshPluginAccess(true).then(enforceCurrentPage);
    },
  });
  return { app };
}
