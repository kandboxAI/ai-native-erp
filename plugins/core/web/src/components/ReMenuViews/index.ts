import { cloneVNode, defineComponent, Fragment, h, type VNode } from "vue";
import { ElTabs } from "element-plus";
import { useRoute } from "vue-router";

/** 独立菜单只挂载指定功能；未配置 menuView 的兼容入口保留原页签。 */
export default defineComponent({
  name: "ReMenuViews",
  inheritAttrs: false,
  props: {
    modelValue: [String, Number],
    viewKey: { type: String, default: "menuView" }
  },
  emits: ["update:modelValue", "tab-change"],
  setup(props, { attrs, slots, emit }) {
    const route = useRoute();
    const menuView = route.meta[props.viewKey];
    const flatten = (nodes: VNode[]): VNode[] =>
      nodes.flatMap(node =>
        node.type === Fragment && Array.isArray(node.children)
          ? flatten(node.children as VNode[])
          : [node]
      );
    const withFilters = (content: VNode[]) =>
      slots.filters
        ? [
            ...(slots.heading?.() || []),
            h("section", { class: "list-query-panel" }, [
              ...(slots.filters() || []),
              ...content
            ])
          ]
        : content;
    // 共享筛选的结构容器可能包住多个 pane；仅投影普通布局节点，不进入其他组件的局部页签。
    const selectContent = (nodes: VNode[]): VNode[] =>
      flatten(nodes).flatMap(node => {
        if ((node.type as { name?: string })?.name === "ElTabPane")
          return String(node.props?.name) === String(menuView)
            ? (node.children as any)?.default?.() || []
            : [];
        if (typeof node.type === "string" && Array.isArray(node.children)) {
          const copy = cloneVNode(node);
          copy.children = selectContent(node.children as VNode[]);
          Object.assign(copy, { dynamicChildren: null });
          copy.patchFlag = 0;
          return [copy];
        }
        return [node];
      });
    return () => {
      if (menuView == null)
        return h(
          ElTabs,
          {
            ...attrs,
            modelValue: props.modelValue,
            "onUpdate:modelValue": value => emit("update:modelValue", value),
            onTabChange: value => emit("tab-change", value)
          },
          { ...slots, default: () => withFilters(slots.default?.() || []) }
        );
      const content = selectContent(slots.default?.() || []);
      return h(
        "section",
        { ...attrs, class: [attrs.class, "list-menu-view"] },
        withFilters(content)
      );
    };
  }
});
