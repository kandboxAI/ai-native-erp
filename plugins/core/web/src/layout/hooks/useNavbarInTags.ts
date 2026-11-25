import { computed } from "vue";
import { useGlobal } from "@pureadmin/utils";
import { useAppStoreHook } from "@/store/modules/app";
import { useSettingStoreHook } from "@/store/modules/settings";

/**
 * 纵向布局的桌面宽度下，顶部操作区并入标签栏，页头只占一行。
 * 移动端、隐藏标签页或全局隐藏侧边栏时保持原有页头结构。
 */
export function useNavbarInTags() {
  const { $storage } = useGlobal<GlobalPropertiesApi>();
  return computed(
    () =>
      $storage?.layout?.layout === "vertical" &&
      !$storage?.configure?.hideTabs &&
      !useSettingStoreHook().hiddenSideBar &&
      useAppStoreHook().device !== "mobile"
  );
}
