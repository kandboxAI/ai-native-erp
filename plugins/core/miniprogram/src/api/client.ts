import { appStore } from "@/store/app";
import { rememberTodoEntry } from "@/utils/todoEntry";

const runtimeEnv = (import.meta as any).env || {};
const defaultApiBaseUrl = runtimeEnv.DEV
  ? "http://127.0.0.1:8000"
  : "";

export const apiBaseUrl = String(
  runtimeEnv.VITE_API_BASE_URL || defaultApiBaseUrl,
).trim().replace(/\/+$/, "");

type HttpMethod = "GET" | "POST" | "PUT" | "DELETE";

interface ApiEnvelope<T> {
  code?: number;
  message?: string;
  detail?: string;
  data?: T;
}

interface RequestOptions {
  method?: HttpMethod;
  path: string;
  data?: Record<string, any>;
  authenticated?: boolean;
  retryOnUnauthorized?: boolean;
  timeout?: number;
}

export class ApiError extends Error {
  statusCode: number;
  business: boolean;

  constructor(message: string, statusCode = 0) {
    super(message);
    this.name = "ApiError";
    this.statusCode = statusCode;
    this.business = statusCode > 0 && statusCode < 500;
  }
}

function compactRequestData(data?: Record<string, any>) {
  return Object.fromEntries(
    Object.entries(data || {}).filter(([, value]) => value !== undefined),
  );
}

function rawRequest<T>(
  options: RequestOptions,
  accessToken?: string,
): Promise<UniApp.RequestSuccessCallbackResult> {
  return new Promise((resolve, reject) => {
    uni.request({
      url: `${apiBaseUrl}${options.path}`,
      method: options.method || "GET",
      data: compactRequestData(options.data),
      header: accessToken
        ? { Authorization: `Bearer ${accessToken}` }
        : undefined,
      timeout: options.timeout || 8000,
      success: resolve,
      fail: (error) => {
        const message = error.errMsg || "网络连接失败";
        if (/invalid url|url not in domain list/i.test(message)) {
          reject(new ApiError(
            "服务地址不可用，请联系管理员检查 HTTPS 地址及微信合法域名",
          ));
        } else {
          reject(new ApiError(message));
        }
      },
    });
  });
}

let refreshTask: Promise<void> | null = null;

async function refreshSession() {
  if (refreshTask) return refreshTask;
  const refreshToken = appStore.state.account?.refreshToken;
  if (!refreshToken) throw new ApiError("登录状态已失效，请重新登录", 401);

  refreshTask = (async () => {
    const response = await rawRequest<{
      access_token: string;
      refresh_token: string;
      expires_in?: number;
      expires_at?: number;
    }>({
      method: "POST",
      path: "/api/auth/refresh",
      data: { refresh_token: refreshToken },
      authenticated: false,
      retryOnUnauthorized: false,
    });
    const body = response.data as ApiEnvelope<{
      access_token: string;
      refresh_token: string;
      expires_in?: number;
      expires_at?: number;
    }>;
    if (response.statusCode !== 200 || body.code !== 0 || !body.data) {
      throw new ApiError(
        body.message || body.detail || "登录状态已失效，请重新登录",
        response.statusCode,
      );
    }
    appStore.updateAccountTokens({
      accessToken: body.data.access_token,
      refreshToken: body.data.refresh_token,
      expiresAt: body.data.expires_at
        ? body.data.expires_at * 1000
        : Date.now() + (body.data.expires_in || 3600) * 1000,
    });
  })().finally(() => {
    refreshTask = null;
  });

  return refreshTask;
}

export function redirectToLogin() {
  appStore.logout();
  const pages = getCurrentPages();
  const current = pages[pages.length - 1]?.route || "";
  const page = pages[pages.length - 1] as { options?: Record<string, string> } | undefined;
  rememberTodoEntry(current, page?.options?.id || "");
  if (current !== "pages/login/index") {
    uni.reLaunch({ url: "/pages/login/index" });
  }
}

/** 分块请求复用普通接口的刷新与登录失效处理。 */
export async function refreshApiSession() {
  try {
    await refreshSession();
  } catch (error) {
    redirectToLogin();
    throw error;
  }
}

export async function requestApi<T>(options: RequestOptions): Promise<T> {
  const authenticated = options.authenticated !== false;
  let response = await rawRequest<T>(
    options,
    authenticated ? appStore.state.account?.accessToken : undefined,
  );

  if (
    response.statusCode === 401 &&
    authenticated &&
    options.retryOnUnauthorized !== false
  ) {
    try {
      await refreshSession();
      response = await rawRequest<T>(
        { ...options, retryOnUnauthorized: false },
        appStore.state.account?.accessToken,
      );
    } catch (error) {
      redirectToLogin();
      throw error;
    }
  }

  const body = response.data as ApiEnvelope<T>;
  if (
    response.statusCode >= 200 &&
    response.statusCode < 300 &&
    body?.code === 0 &&
    body.data !== undefined
  ) {
    return body.data;
  }

  if (response.statusCode === 401 && authenticated) redirectToLogin();
  if (authenticated && [403, 404].includes(response.statusCode) && options.path !== "/api/plugins/miniapp") uni.$emit("miniapp-access-refresh");
  throw new ApiError(
    body?.message || body?.detail || "服务暂不可用，请稍后重试",
    response.statusCode,
  );
}
