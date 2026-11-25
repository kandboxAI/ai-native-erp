import { requestApi } from "./client";
import type { AccountSession } from "@/types";
export interface LoginCaptcha { captchaId: string; image: string; expiresIn: number }
export interface CurrentAccount { tenant_id: string; user_id: string; email?: string | null; display_name?: string | null; avatar_url?: string | null; role_nos?: string[]; role_names?: string[]; permissions?: string[] }
interface LoginResponse { session: { access_token: string; refresh_token: string; expires_in?: number; expires_at?: number }; user: CurrentAccount }
function normalizeSession({ session, user }: LoginResponse): AccountSession {
 return { tenantId: user.tenant_id, userId: user.user_id, email: user.email || "", displayName: user.display_name || "用户", avatarUrl: user.avatar_url || "", roleNames: user.role_names || [], roles: user.role_nos || [], permissions: user.permissions || [], accessToken: session.access_token, refreshToken: session.refresh_token, expiresAt: session.expires_at ? session.expires_at * 1000 : Date.now() + (session.expires_in || 3600) * 1000, role: "standard", department: "" };
}
export async function getLoginCaptcha(): Promise<LoginCaptcha> {
  const result = await requestApi<{
    captcha_id: string;
    image: string;
    expires_in: number;
  }>({
    path: "/api/auth/captcha",
    authenticated: false,
    retryOnUnauthorized: false,
  });
  return {
    captchaId: result.captcha_id,
    image: result.image,
    expiresIn: result.expires_in,
  };
}

export function getCurrentAccount() {
  return requestApi<CurrentAccount>({ path: "/api/auth/me" });
}

export async function loginWithAccount(payload: {
  account: string;
  password: string;
  captchaId: string;
  captchaCode: string;
}) {
  const result = await requestApi<LoginResponse>({
    method: "POST",
    path: "/api/auth/login",
    authenticated: false,
    retryOnUnauthorized: false,
    data: {
      login_name: payload.account.trim(),
      password: payload.password,
      captcha_id: payload.captchaId,
      captcha_code: payload.captchaCode.trim(),
      remember_me: true,
      remember_days: 30,
    },
  });
  return normalizeSession(result);
}

export async function loginWithWechatMiniapp(payload: {
  code: string;
  phoneCode?: string;
}) {
  const result = await requestApi<LoginResponse>({
    method: "POST",
    path: "/api/auth/wechat-miniapp/login",
    authenticated: false,
    retryOnUnauthorized: false,
    data: {
      code: payload.code,
      phone_code: payload.phoneCode,
    },
  });
  return normalizeSession(result);
}
