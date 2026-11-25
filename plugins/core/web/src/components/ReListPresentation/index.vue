<script setup lang="ts">
import { computed, inject, provide, reactive } from "vue";
import { useRoute, useRouter } from "vue-router";
import { resolveRouteTag } from "@/router/routeTag";
import { useAiPageContext } from "@/composables/useAiPageContext";
import { listPresentationKey, listPageKey } from "@/utils/listPresentation";
import { transformI18n } from "@/plugins/i18n";
import type {
  AiFilterValue,
  AiPageContext,
  AiPageSnapshot
} from "@/utils/aiPageContext";

const props = withDefaults(
  defineProps<{
    filters?: Record<string, AiFilterValue>;
    title?: string;
    pageKey?: string;
    dataSource?: AiPageContext["data_source"];
    registerContext?: boolean;
    getSnapshot?: () => AiPageSnapshot;
  }>(),
  { registerContext: true, dataSource: "unknown" }
);
const inherited = inject(listPresentationKey, undefined);
const route = useRoute();
const router = useRouter();
const pageKey = computed(
  () => props.pageKey || listPageKey(route.name || route.path)
);
const title = computed(
  () =>
    props.title ||
    transformI18n(
      resolveRouteTag(route, router.getRoutes())?.meta.title || route.meta.title
    ) ||
    "当前页面"
);
if (!inherited) provide(listPresentationKey, reactive({ pageKey, title }));
if (!inherited && props.registerContext !== false)
  useAiPageContext({
    pageKey,
    title,
    getSnapshot: props.getSnapshot ? () => props.getSnapshot!() : undefined,
    // 只收集调用方显式声明的条件，不读取表格、DOM、任意 URL 参数或业务记录。
    getContext: () => ({
      filters: { ...props.filters },
      data_source: props.dataSource
    })
  });
</script>

<template>
  <div :class="{ 'list-presentation-pilot': !inherited }"><slot /></div>
</template>
