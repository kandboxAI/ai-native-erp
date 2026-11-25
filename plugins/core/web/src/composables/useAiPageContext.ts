import {
  onActivated,
  onDeactivated,
  onBeforeUnmount,
  ref,
  toValue,
  type MaybeRefOrGetter,
  watchEffect
} from "vue";
import { useRoute } from "vue-router";
import { useAiPageContextStore } from "@/store/modules/aiPageContext";
import {
  safeAiFilters,
  type AiPageContext,
  type AiPageSnapshot
} from "@/utils/aiPageContext";

let registration = 0;

/** Register once per page. Leaving, deactivating or changing login clears its metadata. */
export function useAiPageContext(options: {
  pageKey: MaybeRefOrGetter<string>;
  title: MaybeRefOrGetter<string>;
  getContext: () => Pick<AiPageContext, "filters" | "data_source">;
  getSnapshot?: () => AiPageSnapshot;
}) {
  const route = useRoute();
  const context = useAiPageContextStore();
  const owner = `page-context-${++registration}`;
  const initialPath = route.path;
  const ownerRecord = route.matched?.at(-1);
  const revision = context.revision;
  const active = ref(true);
  const release = () => {
    active.value = false;
    context.release(owner);
  };
  watchEffect(() => {
    if (
      !window.erpDesktop ||
      !active.value ||
      (ownerRecord
        ? !route.matched.includes(ownerRecord)
        : route.path !== initialPath) ||
      context.revision !== revision
    ) {
      context.release(owner);
      return;
    }
    const page = options.getContext();
    context.publish(owner, {
      ...page,
      filters: safeAiFilters(page.filters),
      page_key: toValue(options.pageKey),
      title: toValue(options.title),
      path: route.path,
      ...(options.getSnapshot ? { snapshot: options.getSnapshot() } : {})
    });
  });
  onActivated(() => {
    active.value = true;
  });
  onDeactivated(release);
  onBeforeUnmount(release);
}
