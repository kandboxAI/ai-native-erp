import { http } from "@/utils/http";

type ApiResponse<T> = {
  code: number;
  message: string;
  data: T;
};

type LoginParams = {
  username?: string;
  email?: string;
  password?: string;
  captchaId?: string;
  captchaCode?: string;
  rememberMe?: boolean;
  rememberDays?: number;
};

/** 后端 AuthenticatedUser：一个登录账号在一个租户中的用户身份 */
type AuthenticatedUser = {
  auth_user_id: string;
  tenant_id: string;
  tenant_no: string;
  tenant_name?: string | null;
  user_id: string;
  email?: string | null;
  display_name?: string | null;
  avatar_url?: string | null;
  /** 角色编号，仅用于展示；页面与按钮只按 permissions 判断 */
  role_nos: Array<string>;
  permissions: Array<string>;
  profile?: {
    full_name?: string | null;
    avatar_url?: string | null;
  };
};

type LoginData = {
  session: {
    user_id?: string;
    access_token: string;
    refresh_token: string;
    token_type: string;
    expires_in?: number | null;
    expires_at?: number | null;
    remember_me?: boolean;
    session_expires_at?: number | null;
  };
  user: AuthenticatedUser;
};

export type EmployeeQrLoginSession = {
  session_id: string;
  browser_secret: string;
  qr_url: string;
  status: "pending" | "scanned" | "confirmed" | "cancelled" | "consumed";
  expires_in: number;
};

export type EmployeeQrLoginStatus = {
  session_id: string;
  status: "pending" | "scanned" | "confirmed" | "cancelled" | "consumed" | "expired";
  employee_name?: string | null;
  expires_in: number;
};

export type UserResult = {
  code: number;
  message: string;
  data: {
    avatar: string;
    username: string;
    nickname: string;
    roles: Array<string>;
    permissions: Array<string>;
    accessToken: string;
    refreshToken: string;
    expires: Date;
    rememberMe: boolean;
    sessionExpires: number;
    userId?: string;
  };
};

export type RefreshTokenResult = {
  code: number;
  message: string;
  data: {
    accessToken: string;
    refreshToken: string;
    expires: Date;
    rememberMe: boolean;
    sessionExpires: number;
    userId?: string;
  };
};

export type LoginCaptchaResult = {
  captcha_id: string;
  image: string;
  expires_in: number;
};

/** 账户设置-个人信息（来自 /api/auth/me） */
export type UserInfo = {
  avatar_url: string;
  display_name: string;
  full_name: string;
  email: string;
  mobile: string;
  tenant_name: string;
  role_nos: string[];
};

export type UserInfoResult = {
  code: number;
  message: string;
  data: UserInfo;
};

type ResultTable = {
  code: number;
  message: string;
  data?: {
    list: Array<any>;
    total?: number;
    pageSize?: number;
    currentPage?: number;
  };
};

const getExpires = (
  session:
    | LoginData["session"]
    | { expires_at?: number | null; expires_in?: number | null }
) => {
  if (session.expires_at) return new Date(session.expires_at * 1000);
  if (session.expires_in)
    return new Date(Date.now() + session.expires_in * 1000);
  return new Date(Date.now() + 60 * 60 * 1000);
};

const normalizeUserResult = (
  session: LoginData["session"],
  user: AuthenticatedUser
): UserResult => {
  const username =
    user.profile?.full_name ?? user.display_name ?? user.email ?? user.user_id;

  return {
    code: 0,
    message: "success",
    data: {
      avatar: user.avatar_url ?? user.profile?.avatar_url ?? "",
      username,
      nickname: user.display_name ?? username,
      roles: user.role_nos || [],
      permissions: user.permissions ?? [],
      accessToken: session.access_token,
      refreshToken: session.refresh_token,
      expires: getExpires(session),
      rememberMe: session.remember_me === true,
      userId: user.user_id,
      sessionExpires: session.session_expires_at
        ? session.session_expires_at * 1000
        : getExpires(session).getTime()
    }
  };
};

/** 登录 */
export const getLogin = async (data?: LoginParams): Promise<UserResult> => {
  const res = await http.request<ApiResponse<LoginData>>(
    "post",
    "/api/auth/login",
    {
      data: {
        login_name: data?.email ?? data?.username,
        password: data?.password,
        captcha_id: data?.captchaId,
        captcha_code: data?.captchaCode,
        remember_me: data?.rememberMe === true,
        remember_days: data?.rememberDays ?? 7
      }
    }
  );
  return normalizeUserResult(res.data.session, res.data.user);
};

/** 登录图片验证码 */
export const getLoginCaptcha = () => {
  return http.request<ApiResponse<LoginCaptchaResult>>(
    "get",
    "/api/auth/captcha"
  );
};

export const createEmployeeQrLoginSession = () =>
  http.request<ApiResponse<EmployeeQrLoginSession>>(
    "post",
    "/api/auth/employee-qr-login/sessions"
  );

export const getEmployeeQrLoginStatus = (sessionId: string, browserSecret: string) =>
  http.request<ApiResponse<EmployeeQrLoginStatus>>(
    "get",
    `/api/auth/employee-qr-login/sessions/${sessionId}/status`,
    { params: { browser_secret: browserSecret } }
  );

export const exchangeEmployeeQrLogin = async (
  sessionId: string,
  browserSecret: string
): Promise<UserResult> => {
  const res = await http.request<ApiResponse<LoginData>>(
    "post",
    `/api/auth/employee-qr-login/sessions/${sessionId}/exchange`,
    { data: { browser_secret: browserSecret } }
  );
  return normalizeUserResult(res.data.session, res.data.user);
};

/** 当前登录用户 */
export const getCurrentUser = () => {
  return http.request<ApiResponse<AuthenticatedUser>>("get", "/api/auth/me");
};

/** 刷新`token` */
export const refreshTokenApi = async (
  data?: { refreshToken?: string } | string
): Promise<RefreshTokenResult> => {
  const refreshToken =
    typeof data === "string" ? data : data?.refreshToken || "";
  const res = await http.request<
    ApiResponse<{
      user_id?: string;
      access_token: string;
      refresh_token: string;
      expires_in?: number | null;
      expires_at?: number | null;
      remember_me?: boolean;
      session_expires_at?: number | null;
    }>
  >("post", "/api/auth/refresh", {
    data: { refresh_token: refreshToken }
  });

  return {
    code: 0,
    message: "success",
    data: {
      accessToken: res.data.access_token,
      refreshToken: res.data.refresh_token,
      expires: getExpires(res.data),
      rememberMe: res.data.remember_me === true,
      userId: res.data.user_id,
      sessionExpires: res.data.session_expires_at
        ? res.data.session_expires_at * 1000
        : getExpires(res.data).getTime()
    }
  };
};

/** 账户设置-个人信息（当前登录用户） */
export const getMine = async (): Promise<UserInfoResult> => {
  const res = await getCurrentUser();
  const user = res.data;
  const profile = (user?.profile ?? {}) as Record<string, any>;
  return {
    code: res.code,
    message: res.message,
    data: {
      avatar_url: user?.avatar_url ?? profile.avatar_url ?? "",
      display_name: user?.display_name ?? profile.display_name ?? "",
      full_name: profile.full_name ?? user?.display_name ?? "",
      email: user?.email ?? profile.email ?? "",
      mobile: profile.mobile ?? "",
      tenant_name: user?.tenant_name ?? "",
      role_nos: user?.role_nos ?? []
    }
  };
};

/** 账户设置-个人安全日志 */
export const getMineLogs = (data?: object) => {
  return http.request<ResultTable>("get", "/mine-logs", { data });
};
export const saveMyAvatar = (fileId: string) =>
  http.request<ApiResponse<{ avatar_url: string }>>(
    "put",
    "/api/user_profile/me/avatar",
    { data: { file_id: fileId } }
  );
