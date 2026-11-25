import { defineStore } from "pinia";
import {
  type userType,
  store,
  router,
  resetRouter,
  routerArrays,
  storageLocal
} from "../utils";
import {
  type UserResult,
  type RefreshTokenResult,
  getLogin,
  exchangeEmployeeQrLogin,
  getCurrentUser,
  refreshTokenApi
} from "@/api/user";
import { useMultiTagsStoreHook } from "./multiTags";
import {
  type DataInfo,
  getToken,
  setToken,
  removeToken,
  userKey
} from "@/utils/auth";

let refreshInFlight:
  { token: string; promise: Promise<RefreshTokenResult> } | undefined;

export const useUserStore = defineStore("pure-user", {
  state: (): userType => ({
    // 头像
    avatar: storageLocal().getItem<DataInfo<number>>(userKey)?.avatar ?? "",
    // 用户名
    username: storageLocal().getItem<DataInfo<number>>(userKey)?.username ?? "",
    // 昵称
    nickname: storageLocal().getItem<DataInfo<number>>(userKey)?.nickname ?? "",
    // 页面级别权限
    roles: storageLocal().getItem<DataInfo<number>>(userKey)?.roles ?? [],
    // 按钮级别权限
    permissions:
      storageLocal().getItem<DataInfo<number>>(userKey)?.permissions ?? [],
    // 前端生成的验证码（按实际需求替换）
    verifyCode: "",
    // 判断登录页面显示哪个组件（0：登录（默认）、1：手机登录、2：二维码登录、3：注册、4：忘记密码）
    currentPage: 0,
    // 是否勾选了登录页的免登录
    isRemembered: false,
    // 登录页的免登录存储几天，默认7天
    loginDay: 7
  }),
  actions: {
    /** 存储头像 */
    SET_AVATAR(avatar: string) {
      this.avatar = avatar;
    },
    /** 存储用户名 */
    SET_USERNAME(username: string) {
      this.username = username;
    },
    /** 存储昵称 */
    SET_NICKNAME(nickname: string) {
      this.nickname = nickname;
    },
    /** 存储角色 */
    SET_ROLES(roles: Array<string>) {
      this.roles = roles;
    },
    /** 存储按钮级别权限 */
    SET_PERMS(permissions: Array<string>) {
      this.permissions = permissions;
    },
    /** 从服务端同步授权，不刷新令牌或延长登录期限。 */
    async refreshCurrentUser() {
      const initial = getToken();
      if (!initial) throw new Error("登录状态已改变，请重新登录");
      const sameSession = () => {
        const current = getToken();
        return (
          current &&
          current.userId === initial.userId &&
          current.sessionExpires === initial.sessionExpires &&
          (!!initial.userId || current.accessToken === initial.accessToken)
        );
      };
      try {
        const response = await getCurrentUser();
        if (
          !sameSession() ||
          (initial.userId && response.data?.user_id !== initial.userId)
        ) {
          throw new Error("登录状态已改变，请重试");
        }
        if (response.code !== 0 || !response.data)
          throw new Error(response.message || "读取当前权限失败");
        const user = response.data;
        const cached = storageLocal().getItem<DataInfo<number>>(userKey);
        this.SET_PERMS(user.permissions ?? []);
        this.SET_ROLES(user.role_nos ?? []);
        storageLocal().setItem(userKey, {
          ...cached,
          permissions: this.permissions,
          roles: this.roles
        });
        return user;
      } catch (error) {
        if (sameSession()) {
          this.SET_PERMS([]);
          const cached = storageLocal().getItem<DataInfo<number>>(userKey);
          storageLocal().setItem(userKey, { ...cached, permissions: [] });
        }
        throw error;
      }
    },
    /** 存储前端生成的验证码 */
    SET_VERIFYCODE(verifyCode: string) {
      this.verifyCode = verifyCode;
    },
    /** 存储登录页面显示哪个组件 */
    SET_CURRENTPAGE(value: number) {
      this.currentPage = value;
    },
    /** 存储是否勾选了登录页的免登录 */
    SET_ISREMEMBERED(bool: boolean) {
      this.isRemembered = bool;
    },
    /** 设置登录页的免登录存储几天 */
    SET_LOGINDAY(value: number) {
      this.loginDay = Number(value);
    },
    /** 登入 */
    async loginByUsername(data) {
      return new Promise<UserResult>((resolve, reject) => {
        getLogin(data)
          .then(data => {
            if (data.code === 0) {
              setToken(data.data);
              resolve(data);
            } else {
              reject(data.message);
            }
          })
          .catch(error => {
            reject(error);
          });
      });
    },
    /** 微信扫码确认后换取 PC 登录态 */
    async loginByEmployeeQr(sessionId: string, browserSecret: string) {
      const result = await exchangeEmployeeQrLogin(sessionId, browserSecret);
      if (result.code !== 0) throw new Error(result.message || "扫码登录失败");
      setToken(result.data);
      return result;
    },
    /** 前端登出（不调用接口） */
    logOut() {
      this.username = "";
      this.roles = [];
      this.permissions = [];
      removeToken();
      useMultiTagsStoreHook().handleTags("equal", [...routerArrays]);
      resetRouter();
      router.push("/login");
    },
    /** 刷新`token` */
    async handRefreshToken(data) {
      const token = typeof data === "string" ? data : data?.refreshToken;
      if (!token) throw new Error("缺少登录刷新凭据");
      if (refreshInFlight && refreshInFlight.token === token)
        return refreshInFlight.promise;
      const initial = getToken();
      const refresh = async (): Promise<RefreshTokenResult> => {
        let expectedToken = token;
        const current = getToken();
        if (current?.refreshToken !== token) {
          if (!initial?.userId || initial.userId !== current?.userId)
            throw new Error("登录状态已改变，请重试");
          if (current.expires > Date.now()) {
            return {
              code: 0,
              message: "success",
              data: {
                ...current,
                expires: new Date(current.expires),
                rememberMe: current.rememberMe === true,
                sessionExpires: current.sessionExpires
              }
            };
          }
          expectedToken = current.refreshToken;
        }
        const result = await refreshTokenApi({ refreshToken: expectedToken });
        // A response from the previous login must not restore it after logout or an account switch.
        if (getToken()?.refreshToken !== expectedToken)
          throw new Error("登录状态已改变，请重试");
        if (result.code !== 0) throw new Error(result.message);
        setToken(result.data);
        return result;
      };
      // 同一来源的浏览器标签页共用刷新锁，避免重复消费后端凭证。
      const locks = window.navigator?.locks;
      const promise = locks
        ? locks.request("erp-token-refresh", refresh)
        : refresh();
      refreshInFlight = { token, promise };
      try {
        return await promise;
      } finally {
        if (refreshInFlight?.promise === promise) refreshInFlight = undefined;
      }
    }
  }
});

export function useUserStoreHook() {
  return useUserStore(store);
}
