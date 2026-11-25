import { requestApi } from "./client";

export function saveMyAvatar(file_id: string) {
  return requestApi<{ avatar_url: string; file_id: string }>({
    method: "PUT",
    path: "/api/user_profile/me/avatar",
    data: { file_id },
  });
}
