import { http } from "@/utils/http";
import { buildAsyncRoutes, type AuthMenu } from "@/router/authMenuRoutes";

export { buildAsyncRoutes, type AuthMenu } from "@/router/authMenuRoutes";

type ApiResponse<T> = {
  code: number;
  message: string;
  data: T;
};

type Result = {
  code: number;
  message: string;
  data: Array<any>;
};

export const getAsyncRoutes = async () => {
  const res = await http.request<ApiResponse<AuthMenu[]>>(
    "get",
    "/api/auth/menus"
  );
  const routes = buildAsyncRoutes(res.data ?? []);

  return {
    code: 0,
    message: res.message,
    data: routes
  } satisfies Result;
};
