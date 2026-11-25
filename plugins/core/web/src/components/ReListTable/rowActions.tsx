import {
  Comment,
  Fragment,
  Text,
  cloneVNode,
  defineComponent,
  h,
  onBeforeUnmount,
  onMounted,
  onUpdated,
  ref,
  type VNode
} from "vue";
import {
  ElButton,
  ElDropdown,
  ElDropdownItem,
  ElDropdownMenu
} from "element-plus";
import { ArrowDown } from "@element-plus/icons-vue";

/** Only plain actions can move into a menu; confirmation and custom widgets stay intact. */
export function partitionRowActions(nodes: VNode[]) {
  const entries: VNode[] = [];
  function visit(node: VNode) {
    if (
      node.type === Comment ||
      (node.type === Text && !String(node.children).trim())
    )
      return;
    if (node.type === Fragment && Array.isArray(node.children)) {
      (node.children as VNode[]).forEach(visit);
    } else entries.push(node);
  }
  nodes.forEach(visit);
  const plain = entries.every(node => {
    if (node.dirs?.length || node.transition) return false;
    const name = (node.type as any)?.name || (node.type as any)?.__name;
    return (
      name === "ElButton" ||
      (["a", "button", "span"].includes(String(node.type)) &&
        !!node.props?.onClick)
    );
  });
  // 单个剩余操作直接展示，至少两个操作才需要折叠菜单。
  const collapse = plain && entries.length > 3;
  return {
    entries,
    plain,
    inline: collapse ? entries.slice(0, 2) : entries,
    more: collapse ? entries.slice(2) : []
  };
}

export default defineComponent({
  name: "ListRowActions",
  emits: ["measure"],
  setup(_, { slots, emit }) {
    const element = ref<HTMLElement>();
    let observer: ResizeObserver | undefined;
    function measure() {
      const width = element.value?.getBoundingClientRect?.().width;
      if (width != null) emit("measure", Math.ceil(width));
    }
    onMounted(() => {
      if (typeof ResizeObserver !== "undefined" && element.value) {
        observer = new ResizeObserver(measure);
        observer.observe(element.value);
      }
      measure();
    });
    onUpdated(measure);
    onBeforeUnmount(() => observer?.disconnect());
    return () => {
      const { entries, plain, inline, more } = partitionRowActions(
        slots.default?.() || []
      );
      return h(
        "div",
        {
          ref: element,
          class: ["list-row-actions", { "list-row-actions-custom": !plain }],
          onClick: (event: MouseEvent) => event.stopPropagation()
        },
        [
          ...(plain ? inline : entries),
          ...(more.length
            ? [
                h(
                  ElDropdown,
                  { trigger: "click", placement: "bottom-end" },
                  {
                    default: () =>
                      h(
                        ElButton,
                        {
                          link: true,
                          type: "primary",
                          "data-action": "neutral",
                          "aria-label": "更多操作"
                        },
                        {
                          default: () => [
                            "更多",
                            h(ArrowDown, { class: "list-row-actions-arrow" })
                          ]
                        }
                      ),
                    dropdown: () =>
                      h(
                        ElDropdownMenu,
                        { class: "list-row-actions-menu" },
                        {
                          default: () =>
                            more.map((node, index) =>
                              h(
                                ElDropdownItem,
                                {
                                  key: node.key ?? index,
                                  disabled: !!(
                                    node.props?.disabled || node.props?.loading
                                  ),
                                  divided:
                                    node.props?.["data-action"]
                                      ? node.props["data-action"] === "danger"
                                      : node.props?.type === "danger" ||
                                        node.props?.["data-list-action"] ===
                                          "delete",
                                  onClick: (event: MouseEvent) => {
                                    // Keyboard activation targets the menu item. Let the original action handle it.
                                    if (event.target === event.currentTarget)
                                      (
                                        (event.currentTarget as HTMLElement)
                                          .firstElementChild as HTMLElement
                                      )?.click();
                                  }
                                },
                                {
                                  default: () =>
                                    cloneVNode(node, { tabindex: -1 })
                                }
                              )
                            )
                        }
                      )
                  }
                )
              ]
            : [])
        ]
      );
    };
  }
});
