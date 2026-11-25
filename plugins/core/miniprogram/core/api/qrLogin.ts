import { requestApi } from "./client";

export function confirmPcWechatLogin(
  scene: string,
  payload: { code: string; phoneCode?: string; confirm: boolean },
) {
  return requestApi<{
    status: string;
    bound: boolean;
    requires_phone: boolean;
    employee_name?: string | null;
  }>({
    method: "POST",
    path: `/api/auth/employee-qr-login/mobile/${encodeURIComponent(scene)}/wechat`,
    authenticated: false,
    retryOnUnauthorized: false,
    data: {
      code: payload.code,
      phone_code: payload.phoneCode,
      confirm: payload.confirm,
    },
  });
}

