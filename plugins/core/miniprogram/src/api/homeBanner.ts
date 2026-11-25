import { requestApi } from "./client";

export interface HomeBanner {
  id: string;
  image: { id: string; url: string; file_name: string; width?: number | null; height?: number | null } | null;
}

export function fetchHomeBanners() {
  return requestApi<{ items: HomeBanner[] }>({ path: "/api/miniapp_menu/home-banners" });
}
