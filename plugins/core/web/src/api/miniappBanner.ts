import { http } from "@/utils/http";
import type { FileItem } from "@/api/systemFile";
import type { ApiResponse } from "@/api/miniappMenu";

export interface MiniappBanner {
  id: string;
  org_id: string;
  sort_no: number;
  is_active: boolean;
  image: Pick<FileItem, "id" | "file_name" | "url" | "width" | "height"> | null;
}
export interface MiniappBannerPayload {
  file_id: string;
  sort_no: number;
  is_active: boolean;
}
const base = "/api/miniapp_menu/banners";
export const listMiniappBanners = () =>
  http.request<ApiResponse<{ items: MiniappBanner[] }>>("get", base);
export const saveMiniappBanner = (
  id: string | null,
  data: MiniappBannerPayload
) =>
  http.request<ApiResponse<MiniappBanner>>(
    id ? "put" : "post",
    id ? `${base}/${id}` : base,
    { data }
  );
export const deleteMiniappBanner = (id: string) =>
  http.request<ApiResponse<{ deleted: boolean }>>("delete", `${base}/${id}`);

/** 当前登录用户可见的首页图片；不要求轮播图管理权限。 */
export const listHomeBanners = () =>
  http.request<ApiResponse<{ items: MiniappBanner[] }>>(
    "get",
    "/api/miniapp_menu/home-banners"
  );
