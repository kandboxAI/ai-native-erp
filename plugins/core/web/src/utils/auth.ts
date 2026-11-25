import Cookies from "js-cookie";
import { store } from "@/store";
import { useAiPageContextStore } from "@/store/modules/aiPageContext";
import { useUserStoreHook } from "@/store/modules/user";
import { storageLocal, isString, isIncludeAllChildren } from "@pureadmin/utils";

export interface DataInfo<T> {
  /** token */
  accessToken: string;
  /** `accessToken`的过期时间（时间戳） */
  expires: T;
  /** 用于调用刷新accessToken的接口时所需的token */
  refreshToken: string;
  /** 后端确认的跨重启保留登录策略 */
  rememberMe?: boolean;
  /** 后端登录会话的固定截止时间（毫秒时间戳） */
  sessionExpires?: number;
  /** 用于区分刷新凭证轮换与切换账号 */
  userId?: string;
  /** 头像 */
  avatar?: string;
  /** 用户名 */
  username?: string;
  /** 昵称 */
  nickname?: string;
  /** 当前登录用户的角色 */
  roles?: Array<string>;
  /** 当前登录用户的按钮级别权限 */
  permissions?: Array<string>;
}

export const userKey = "user-info";
export const TokenKey = "authorized-token";
export const asyncRoutesKey = "async-routes-v2";
const legacyAsyncRoutesKey = "async-routes";
/**
 * 浏览器多标签页的兼容标记；登录恢复以令牌和后端截止时间为准。
 * */
export const multipleTabsKey = "multiple-tabs";

/** 动态路由属于当前登录身份，切换账号或升级缓存结构时必须清除。 */
export function clearAsyncRoutesCache() {
  storageLocal().removeItem(asyncRoutesKey);
  storageLocal().removeItem(legacyAsyncRoutesKey);
}

/** 从 Cookie 或本地存储读取当前登录令牌。 */
export function getToken(): DataInfo<number> | null {
  const cookie = Cookies.get(TokenKey);
  if (cookie) {
    try {
      const token = JSON.parse(cookie) as DataInfo<number>;
      if (token?.accessToken) return token;
    } catch {
      // Ignore an invalid cookie and try the desktop storage fallback.
    }
  }
  const temporary = window.sessionStorage.getItem(TokenKey);
  if (temporary) {
    try {
      const token = JSON.parse(temporary) as DataInfo<number>;
      if (token?.accessToken) return token;
    } catch {
      window.sessionStorage.removeItem(TokenKey);
    }
  }
  const token = storageLocal().getItem<DataInfo<number>>(TokenKey);
  // 旧版本桌面令牌没有免登录策略，升级后需要重新登录一次。
  return token?.accessToken && token.rememberMe && token.sessionExpires
    ? token
    : null;
}

/** 登录恢复时校验后端给出的固定截止时间。 */
export function isLoginSessionActive(): boolean {
  const token = getToken();
  return (
    !!token?.accessToken && (token.sessionExpires ?? token.expires) > Date.now()
  );
}

/**
 * @description 设置`token`以及一些必要信息并采用无感刷新`token`方案
 * 无感刷新：后端返回`accessToken`（访问接口使用的`token`）、`refreshToken`（用于调用刷新`accessToken`的接口时所需的`token`，`refreshToken`的过期时间（比如30天）应大于`accessToken`的过期时间（比如2小时））、`expires`（`accessToken`的过期时间）
 * 免登录令牌保存在本地存储，临时登录令牌保存在当前窗口；Cookie 支持浏览器多标签页。
 * 登录截止时间由后端返回，刷新令牌后也不能延长；用户资料不保存刷新凭证。
 */
export function setToken(data: DataInfo<Date>) {
  if (data.userId !== undefined && getToken()?.userId !== data.userId)
    useAiPageContextStore(store).resetContext();
  clearAsyncRoutesCache();
  let expires = 0;
  const { accessToken, refreshToken } = data;
  if (accessToken)
    void window.erpDesktop
      ?.bindErpSession(accessToken)
      .catch(() => undefined);
  expires = new Date(data.expires).getTime(); // 如果后端直接设置时间戳，将此处代码改为expires = data.expires，然后把上面的DataInfo<Date>改成DataInfo<number>即可
  const rememberMe = data.rememberMe === true;
  const sessionExpires = data.sessionExpires ?? expires;
  const userId = data.userId ?? getToken()?.userId;
  const token = {
    accessToken,
    expires,
    refreshToken,
    rememberMe,
    sessionExpires,
    userId
  };
  const cookieString = JSON.stringify(token);
  const cookieOptions =
    rememberMe && sessionExpires > Date.now()
      ? { expires: new Date(sessionExpires) }
      : {};
  Cookies.set(TokenKey, cookieString, cookieOptions);

  if (rememberMe) {
    storageLocal().setItem(TokenKey, token);
    window.sessionStorage.removeItem(TokenKey);
  } else {
    window.sessionStorage.setItem(TokenKey, cookieString);
    storageLocal().removeItem(TokenKey);
  }
  Cookies.set(multipleTabsKey, "true", cookieOptions);

  function setUserKey({ avatar, username, nickname, roles, permissions }) {
    useUserStoreHook().SET_AVATAR(avatar);
    useUserStoreHook().SET_USERNAME(username);
    useUserStoreHook().SET_NICKNAME(nickname);
    useUserStoreHook().SET_ROLES(roles);
    useUserStoreHook().SET_PERMS(permissions);
    storageLocal().setItem(userKey, {
      avatar,
      username,
      nickname,
      roles,
      permissions
    });
  }

  if (data.username && data.roles) {
    const { username, roles } = data;
    setUserKey({
      avatar: data?.avatar ?? "",
      username,
      nickname: data?.nickname ?? "",
      roles,
      permissions: data?.permissions ?? []
    });
  } else {
    const avatar =
      storageLocal().getItem<DataInfo<number>>(userKey)?.avatar ?? "";
    const username =
      storageLocal().getItem<DataInfo<number>>(userKey)?.username ?? "";
    const nickname =
      storageLocal().getItem<DataInfo<number>>(userKey)?.nickname ?? "";
    const roles =
      storageLocal().getItem<DataInfo<number>>(userKey)?.roles ?? [];
    const permissions =
      storageLocal().getItem<DataInfo<number>>(userKey)?.permissions ?? [];
    setUserKey({
      avatar,
      username,
      nickname,
      roles,
      permissions
    });
  }
}

/** 删除`token`以及key值为`user-info`的localStorage信息 */
export function removeToken() {
  useAiPageContextStore(store).resetContext();
  void window.erpDesktop?.clearErpSession().catch(() => undefined);
  Cookies.remove(TokenKey);
  Cookies.remove(multipleTabsKey);
  storageLocal().removeItem(TokenKey);
  window.sessionStorage.removeItem(TokenKey);
  storageLocal().removeItem(userKey);
  clearAsyncRoutesCache();
}

/** 格式化token（jwt格式） */
export const formatToken = (token: string): string => {
  return "Bearer " + token;
};

/** 是否有按钮级别的权限（根据登录接口返回的`permissions`字段进行判断）*/
export const hasPerms = (value: string | Array<string>): boolean => {
  if (!value) return false;
  const allPerms = "*:*:*";
  const { permissions } = useUserStoreHook();
  if (!permissions) return false;
  if (permissions.length === 1 && permissions[0] === allPerms) return true;
  const isAuths = isString(value)
    ? permissions.includes(value)
    : isIncludeAllChildren(value, permissions);
  return isAuths ? true : false;
};
