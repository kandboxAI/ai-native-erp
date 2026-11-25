import { http } from "@/utils/http";

export type ApiResponse<T> = {
  code: number;
  message: string;
  data: T;
};

export type UserFavoriteMenu = {
  menu_id: string;
  menu_key: string;
  menu_name: string;
  path: string;
  icon: string | null;
  ancestor_names: string[];
};

export type UserFavoriteConfig = {
  items: UserFavoriteMenu[];
  candidates: UserFavoriteMenu[];
  max_count: number;
};

export const getUserFavoriteConfig = () =>
  http.request<ApiResponse<UserFavoriteConfig>>("get", "/api/menu/favorites");

export const saveUserFavoriteConfig = (menuIds: string[]) =>
  http.request<ApiResponse<UserFavoriteConfig>>("put", "/api/menu/favorites", {
    data: { menu_ids: menuIds }
  });
