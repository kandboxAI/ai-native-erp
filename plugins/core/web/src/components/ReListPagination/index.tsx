import {
  computed,
  defineComponent,
  getCurrentInstance,
  h,
  nextTick,
  onBeforeUnmount,
  onMounted,
  ref,
  type PropType
} from "vue";
import { ElPagination } from "element-plus";

export const LIST_PAGE_SIZES = [10, 20, 50, 100];

/** 菜单、局部列表和 Pure 表格共用分页外观与切换协议。 */
export default defineComponent({
  name: "ReListPagination",
  inheritAttrs: false,
  props: {
    currentPage: { type: Number, default: 1 },
    pageSize: { type: Number, default: 20 },
    total: { type: Number, default: 0 },
    disabled: Boolean,
    fixedPageSize: Boolean,
    pageSizes: {
      type: Array as PropType<number[]>,
      default: () => LIST_PAGE_SIZES
    }
  },
  emits: [
    "update:currentPage",
    "update:pageSize",
    "current-change",
    "size-change",
    "change"
  ],
  setup(props, { attrs, emit }) {
    const instance = getCurrentInstance()!;
    const container = ref<HTMLElement>();
    const width = ref(800);
    let observer: ResizeObserver | undefined;
    onMounted(() => {
      if (typeof ResizeObserver !== "undefined" && container.value) {
        observer = new ResizeObserver(([entry]) => {
          width.value = entry.contentRect.width;
        });
        observer.observe(container.value);
      }
    });
    onBeforeUnmount(() => observer?.disconnect());
    const listeners = () => instance.vnode.props || {};
    const canResize = () =>
      !props.fixedPageSize &&
      !!(listeners()["onUpdate:pageSize"] || listeners().onSizeChange);
    // 保留已有的合法每页条数，不能因候选项改变而在首次渲染时触发查询。
    const sizes = computed(() =>
      [...new Set([...props.pageSizes, props.pageSize])].sort((a, b) => a - b)
    );
    let resizing = false;
    let pendingPage: number | undefined;
    function currentChange(page: number) {
      if (resizing || page === props.currentPage || page === pendingPage)
        return;
      pendingPage = page;
      emit("update:currentPage", page);
      emit("current-change", page);
      emit("change", page, props.pageSize);
      nextTick(() => {
        pendingPage = undefined;
      });
    }
    async function sizeChange(size: number) {
      if (!canResize() || size === props.pageSize) return;
      resizing = true;
      // 先更新全部查询参数，再通知查询；与只监听 v-model 的本地分页兼容。
      emit("update:pageSize", size);
      emit("update:currentPage", 1);
      emit("size-change", size);
      if (!listeners().onSizeChange) emit("current-change", 1);
      emit("change", 1, size);
      await nextTick();
      resizing = false;
    }
    return () => {
      const shared = {
        ...attrs,
        class: "list-pagination-control",
        style: undefined,
        currentPage: props.currentPage,
        pageSize: props.pageSize,
        total: props.total,
        disabled: props.disabled,
        pageSizes: sizes.value,
        background: true,
        size: "default" as const,
        small: false,
        pagerCount: width.value < 600 ? 5 : 7,
        hideOnSinglePage: false,
        // 不转发 Element 因总数或每页条数变化触发的二次页码事件。
        "onUpdate:currentPage": currentChange,
        "onUpdate:pageSize": sizeChange,
        onCurrentChange: undefined,
        onSizeChange: undefined,
        onChange: undefined
      };
      return h(
        "div",
        {
          ref: container,
          class: ["list-pagination", attrs.class],
          style: attrs.style
        },
        [
          h(
            ElPagination,
            {
              ...shared,
              layout: canResize()
                ? "total, sizes, slot, jumper"
                : "total, slot, jumper"
            },
            {
              default: () => [
                !canResize() &&
                  h(
                    "span",
                    { class: "list-pagination-fixed-size" },
                    `${props.pageSize} 条/页`
                  ),
                h(
                  ElPagination,
                  {
                    ...shared,
                    layout:
                      width.value < 480
                        ? "prev, slot, next"
                        : "prev, pager, next",
                    class: "list-pagination-pages"
                  },
                  {
                    default: () =>
                      h(
                        "span",
                        { class: "list-pagination-current" },
                        `${props.currentPage} / ${Math.max(1, Math.ceil(props.total / props.pageSize))}`
                      )
                  }
                )
              ]
            }
          )
        ]
      );
    };
  }
});
