import { http } from "@/utils/http";

export type PluginState = {
  plugin_key: string;
  name: string;
  version: string;
  requires: string[];
  installed_version: string | null;
  upgrade_available: boolean;
  provisioning_status_code: "pending" | "installing" | "ready" | "failed";
  is_active: boolean;
  enabled_at: string | null;
  last_error_type: string | null;
};

type ApiResponse<T> = { code: number; message: string; data: T };

export type SuiteState = {
  suite_key: string;
  name: string;
  version: string;
  plugins: string[];
  components: PluginState[];
  is_active: boolean;
  is_ready: boolean;
  upgrade_available: boolean;
  provisioning_status_code: PluginState["provisioning_status_code"];
};

export const listSuites = () =>
  http.request<ApiResponse<SuiteState[]>>("get", "/api/plugins/suites");

export const changeSuite = (
  key: string,
  action: "enable" | "disable" | "upgrade"
) =>
  http.request<
    ApiResponse<
      SuiteState & {
        completed_plugins: string[];
        retained_plugins: { plugin_key: string; required_by: string[] }[];
      }
    >
  >("post", `/api/plugins/suites/${encodeURIComponent(key)}/${action}`, {
    timeout: 900000
  });

export const listPlugins = () =>
  http.request<ApiResponse<PluginState[]>>("get", "/api/plugins");

export const setPluginActive = (key: string, active: boolean) =>
  http.request<ApiResponse<PluginState>>(
    "post",
    `/api/plugins/${encodeURIComponent(key)}/${active ? "enable" : "disable"}`,
    { timeout: 300000 }
  );

export const upgradePlugin = (key: string) =>
  http.request<ApiResponse<PluginState>>(
    "post",
    `/api/plugins/${encodeURIComponent(key)}/upgrade`,
    { timeout: 300000 }
  );
