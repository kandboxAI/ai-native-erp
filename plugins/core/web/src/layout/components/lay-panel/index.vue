<script setup lang="ts">
import { useI18n } from "vue-i18n";
import { emitter } from "@/utils/mitt";
import { onClickOutside, onKeyStroke } from "@vueuse/core";
import { ref, computed, watch, onMounted, onBeforeUnmount } from "vue";
import { useDataThemeChange } from "@/layout/hooks/useDataThemeChange";
import CloseIcon from "~icons/ep/close";

const target = ref(null);
const show = ref(false);

// 原生助手视图不参与网页层叠，打开设置时需先让出显示区域。
watch(
  show,
  visible => {
    void window.erpDesktop?.setAssistantObscured(visible);
  },
  { flush: "sync" }
);
onKeyStroke("Escape", () => {
  show.value = false;
});

const iconClass = computed(() => {
  return [
    "size-5.5",
    "flex-c",
    "outline-hidden",
    "rounded-sm",
    "cursor-pointer",
    "transition-colors",
    "hover:bg-[#0000000f]",
    "dark:hover:bg-[#ffffff1f]",
    "dark:hover:text-[#ffffffd9]"
  ];
});

const { t } = useI18n();
const { onReset } = useDataThemeChange();

onClickOutside(
  target,
  (event: any) => {
    if (event.clientX > target.value.offsetLeft) return;
    show.value = false;
  },
  { ignore: [".settings-color-popper"] }
);

onMounted(() => {
  emitter.on("openPanel", () => {
    show.value = true;
  });
});

onBeforeUnmount(() => {
  // 解绑`openPanel`公共事件，防止多次触发
  emitter.off("openPanel");
  if (show.value) void window.erpDesktop?.setAssistantObscured(false);
});
</script>

<template>
  <div :class="{ show }">
    <div class="right-panel-background" />
    <div ref="target" class="right-panel bg-bg_color">
      <div
        class="right-panel-header flex-bc py-3 px-5 border-0 border-l border-solid border-(--pure-border-color)"
      >
        <h4 class="dark:text-white">
          {{ t("panel.pureSystemSet") }}
        </h4>
        <span
          v-tippy="{
            content: t('panel.pureCloseSystemSet'),
            placement: 'bottom-start',
            zIndex: 41000
          }"
          :class="iconClass"
        >
          <IconifyIconOffline
            class="dark:text-white"
            width="18px"
            height="18px"
            :icon="CloseIcon"
            @click="show = !show"
          />
        </span>
      </div>
      <el-scrollbar
        class="right-panel-body border-y border-l border-r-0 border-solid border-(--pure-border-color)"
      >
        <slot />
      </el-scrollbar>

      <div
        class="right-panel-footer flex justify-end p-3 border-0 border-l border-solid border-(--pure-border-color)"
      >
        <el-button
          v-tippy="{
            content: t('panel.pureClearCacheAndToLogin'),
            placement: 'left-start',
            zIndex: 41000
          }"
          type="danger"
          text
          bg
          @click="onReset"
        >
          {{ t("panel.pureClearCache") }}
        </el-button>
      </div>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.right-panel-background {
  position: fixed;
  top: 0;
  left: 0;
  z-index: -1;
  background: rgb(0 0 0 / 20%);
  opacity: 0;
  transition: opacity 0.3s cubic-bezier(0.7, 0.3, 0.1, 1);
}

.right-panel {
  position: fixed;
  top: 0;
  right: 0;
  z-index: 40000;
  display: flex;
  flex-direction: column;
  width: 100%;
  max-width: 280px;
  height: 100dvh;
  box-shadow: 0 0 15px 0 rgb(0 0 0 / 5%);
  transform: translate(100%);
  transition: all 0.25s cubic-bezier(0.7, 0.3, 0.1, 1);
}

.right-panel-header,
.right-panel-footer {
  flex: none;
}

.right-panel-body {
  flex: 1;
  min-height: 0;
}

.show {
  transition: all 0.3s cubic-bezier(0.7, 0.3, 0.1, 1);

  .right-panel-background {
    z-index: 20000;
    width: 100%;
    height: 100%;
    opacity: 1;
  }

  .right-panel {
    transform: translate(0);
  }
}
</style>
