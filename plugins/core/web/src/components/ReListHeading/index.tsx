import { defineComponent, inject } from "vue";
import { useRoute, useRouter } from "vue-router";
import { dialogInjectionKey } from "element-plus";
import { resolveRouteTag } from "@/router/routeTag";
import { transformI18n } from "@/plugins/i18n";
import AiEntry from "@/components/AiEntry/index.vue";
import { listPresentationKey } from "@/utils/listPresentation";

export default defineComponent({
  name: "ReListHeading",
  props: { title: { type: String, default: "" } },
  setup(props, { slots }) {
    const route = useRoute();
    const router = useRouter();
    const presentation = inject(listPresentationKey, undefined);
    // 弹窗已有标题，复用列表时不再渲染页面标题卡片和 AI 入口。
    const inDialog = inject(dialogInjectionKey, undefined);
    const showAiEntry = presentation && !inDialog;
    if (inDialog)
      return () =>
        slots.default || slots.actions ? (
          <div class="list-heading-content">
            {slots.default?.()}
            {slots.actions?.()}
          </div>
        ) : null;
    return () => (
      <header
        class={[
          "list-page-heading list-card-title",
          presentation && "list-page-heading--pilot"
        ]}
      >
        <div class="list-heading-main">
          {slots.heading ? (
            slots.heading()
          ) : (
            <h2>
              {slots.title?.() ||
                props.title ||
                transformI18n(
                  String(
                    resolveRouteTag(route, router.getRoutes())?.meta.title ||
                      route.meta.title ||
                      "数据列表"
                  )
                )}
            </h2>
          )}
          {slots.default && (
            <div class="list-heading-content">{slots.default()}</div>
          )}
        </div>
        {(showAiEntry || slots.actions) && (
          <div class="list-heading-actions">
            {slots.actions?.()}
            {showAiEntry && (
              <AiEntry
                appearance="button"
                subjectKey={`${presentation.pageKey}.page`}
                subjectTitle={presentation.title}
                questions={[
                  {
                    key: "explain",
                    label: "解释页面字段与操作",
                    prompt: `请解释“${presentation.title}”的主要字段和常见操作。`
                  },
                  {
                    key: "review",
                    label: "帮助核对需要关注的事项",
                    prompt: `请在我的权限范围内，帮助核对“${presentation.title}”需要关注的事项，说明查询范围和数据来源；数据不足时请明确说明。`
                  }
                ]}
              />
            )}
          </div>
        )}
      </header>
    );
  }
});
