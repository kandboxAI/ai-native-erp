import { getToken } from "@/utils/auth";
import { useUserStoreHook } from "@/store/modules/user";
import { message } from "@/utils/message";

/** Recover the desktop gateway login; only a rejected login sends the user to ERP login. */
export function installDesktopSession(): () => void {
  const bridge = window.erpDesktop;
  if (!bridge?.onErpSessionExpired) return () => {};
  let active = true;
  let recovering = false;
  let retryDelay = 1000;
  let timer: ReturnType<typeof setTimeout> | undefined;

  const requireLogin = () => {
    useUserStoreHook().logOut();
    message("登录已失效，请重新登录 ERP。原来的聊天记录会保留。", {
      type: "warning"
    });
  };

  const recover = async () => {
    if (!active || recovering) return;
    if (timer) clearTimeout(timer);
    timer = undefined;
    const session = getToken();
    if (!session?.refreshToken) {
      requireLogin();
      return;
    }
    recovering = true;
    let expectedToken = session.accessToken;
    try {
      const result = await useUserStoreHook().handRefreshToken({
        refreshToken: session.refreshToken
      });
      if (!active || getToken()?.accessToken !== result.data.accessToken)
        return;
      expectedToken = result.data.accessToken;
      await bridge.bindErpSession(expectedToken);
      retryDelay = 1000;
    } catch (error) {
      if (!active || getToken()?.accessToken !== expectedToken) return;
      const failure = error as {
        response?: { status?: number };
        message?: string;
      };
      if (
        failure?.response?.status === 401 ||
        failure?.message?.includes("ERP_SESSION_EXPIRED:")
      ) {
        requireLogin();
      } else {
        // A backend restart or timeout must not sign the user out.
        // The main process retries gateway issuance after a successful ERP refresh.
        if (expectedToken !== session.accessToken) return;
        timer = setTimeout(() => void recover(), retryDelay);
        retryDelay = Math.min(30_000, retryDelay * 2);
      }
    } finally {
      recovering = false;
    }
  };

  const unsubscribe = bridge.onErpSessionExpired(() => void recover());
  const dispose = () => {
    active = false;
    if (timer) clearTimeout(timer);
    unsubscribe();
  };
  if (import.meta.hot) import.meta.hot.dispose(dispose);
  return dispose;
}
