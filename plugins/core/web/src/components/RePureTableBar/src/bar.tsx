import { $t, transformI18n } from "@/plugins/i18n";
import type { CheckboxValueType } from "element-plus";
import {
  type PropType,
  ref,
  provide,
  watch,
  Fragment,
  computed,
  defineComponent
} from "vue";
import { useRoute } from "vue-router";
import ReListHeading from "@/components/ReListHeading/index";
import {
  readListPreference,
  saveListPreference,
  clearListPreference,
  mergeColumnPreferences,
  columnKeys
} from "@/utils/listState";
import { cloneDeep, isBoolean, isFunction, getKeyList } from "@pureadmin/utils";

import PinAngle from "~icons/bi/pin-angle";
import PinAngleFill from "~icons/bi/pin-angle-fill";
import DragIcon from "@/assets/table-bar/drag.svg?component";
import ExpandIcon from "@/assets/table-bar/expand.svg?component";
import SettingIcon from "@/assets/table-bar/settings.svg?component";

const props = {
  listHeading: { type: Boolean, default: true },
  /** 头部最左边的标题 */
  title: {
    type: String,
    default: $t("tableBar.pureList")
  },
  /** 对于树形表格，如果想启用展开和折叠功能，传入当前表格的ref即可 */
  tableRef: {
    type: Object as PropType<any>
  },
  /** 需要展示的列 */
  columns: {
    type: Array as PropType<TableColumnList>,
    default: () => []
  },
  isExpandAll: {
    type: Boolean,
    default: true
  },
  tableKey: {
    type: [String, Number] as PropType<string | number>,
    default: "0"
  }
};

export default defineComponent({
  name: "PureTableBar",
  props,
  emits: ["refresh", "fullscreen"],
  setup(props, { emit, slots, attrs }) {
    const route = useRoute();
    provide("list-columns-managed", true);
    provide("list-refresh", () => emit("refresh"));
    const size = ref("default");
    const checkAll = ref(true);
    const isIndeterminate = ref(false);
    const draggingLabel = ref("");
    const isExpandAll = ref(props.isExpandAll);
    let filterColumns = cloneDeep(props?.columns).filter(column =>
      isBoolean(column?.hide)
        ? !column.hide
        : !(isFunction(column?.hide) && column?.hide())
    );
    let checkColumnList = getKeyList(cloneDeep(props?.columns), "label");
    const checkedColumns = ref(getKeyList(cloneDeep(filterColumns), "label"));
    const dynamicColumns = ref(cloneDeep(props?.columns));
    const preferenceId = () =>
      `${route.path}:${String(route.meta.entity || route.meta.report || "")}:${props.tableKey}`;
    const locked = column => !!column.type || column.slot === "operation";
    watch(
      () => [
        props.columns,
        props.columns.map(column =>
          isFunction(column.hide) ? column.hide() : column.hide
        ),
        props.tableKey,
        route.path,
        route.meta.entity,
        route.meta.report
      ],
      () => {
        const source = props.columns.filter(
          column => !(isFunction(column.hide) && column.hide())
        );
        const keys = columnKeys(source);
        const columns = cloneDeep(source).map((column, index) => ({
          ...column,
          key: keys[index],
          locked: locked(column),
          hidden: isFunction(column.hide) ? column.hide() : !!column.hide
        }));
        const preference = readListPreference(preferenceId());
        dynamicColumns.value = mergeColumnPreferences(
          columns,
          preference?.columns
        ).map(column => ({
          ...column,
          hide: column.locked ? false : column.hidden
        }));
        filterColumns = dynamicColumns.value.filter(column => !column.hide);
        checkColumnList = getKeyList(dynamicColumns.value, "label");
        checkedColumns.value = getKeyList(filterColumns, "label");
        checkAll.value = filterColumns.length === columns.length;
        isIndeterminate.value = filterColumns.length > 0 && !checkAll.value;
        size.value = preference?.size || "default";
      },
      { deep: true, immediate: true }
    );
    watch(
      [dynamicColumns, size],
      () => {
        if (!props.columns.length) return;
        const keys = columnKeys(dynamicColumns.value);
        saveListPreference(preferenceId(), {
          version: 1,
          size: size.value as "large" | "default" | "small",
          columns: dynamicColumns.value.map((column, index) => ({
            key: keys[index],
            hidden: locked(column) ? false : !!column.hide,
            fixed: column.fixed === true ? "right" : column.fixed || false
          }))
        });
      },
      { deep: true }
    );

    const iconClass = computed(() => {
      return [
        "text-black",
        "dark:text-white",
        "duration-100",
        "hover:text-primary!",
        "cursor-pointer",
        "outline-hidden"
      ];
    });

    const topClass = computed(() => {
      return [
        "flex",
        "justify-between",
        "pt-0.75",
        "px-2.75",
        "border-b",
        "border-b-solid",
        "border-[#dcdfe6]",
        "dark:border-[#303030]"
      ];
    });

    function onExpand() {
      isExpandAll.value = !isExpandAll.value;
      toggleRowExpansionAll(props.tableRef.data, isExpandAll.value);
    }

    function toggleRowExpansionAll(data, isExpansion) {
      data.forEach(item => {
        props.tableRef.toggleRowExpansion(item, isExpansion);
        if (item.children !== undefined && item.children !== null) {
          toggleRowExpansionAll(item.children, isExpansion);
        }
      });
    }

    function handleCheckAllChange(val: CheckboxValueType) {
      checkedColumns.value = val
        ? checkColumnList
        : getKeyList(dynamicColumns.value.filter(locked), "label");
      isIndeterminate.value = false;
      dynamicColumns.value.map(column =>
        val || locked(column) ? (column.hide = false) : (column.hide = true)
      );
    }

    function handleCheckedColumnsChange(value: CheckboxValueType[]) {
      checkedColumns.value = value;
      const checkedCount = value.length;
      checkAll.value = checkedCount === checkColumnList.length;
      isIndeterminate.value =
        checkedCount > 0 && checkedCount < checkColumnList.length;
    }

    function handleCheckColumnListChange(
      val: CheckboxValueType,
      label: string
    ) {
      const column = dynamicColumns.value.find(
        item => transformI18n(item.label) === transformI18n(label)
      );
      if (!column || locked(column)) return;
      dynamicColumns.value.filter(
        item => transformI18n(item.label) === transformI18n(label)
      )[0].hide = !val;
    }

    function handleToggleColumnFixed(fixed, label: string) {
      const column = dynamicColumns.value.find(
        item => transformI18n(item.label) === transformI18n(label)
      );
      if (column) {
        column.fixed = fixed;
      }
    }

    function onReset() {
      clearListPreference(preferenceId());
      dynamicColumns.value = cloneDeep(
        props.columns.filter(
          column => !(isFunction(column.hide) && column.hide())
        )
      );
      checkColumnList = getKeyList(dynamicColumns.value, "label");
      filterColumns = dynamicColumns.value.filter(
        column =>
          locked(column) ||
          !(isFunction(column.hide) ? column.hide() : column.hide)
      );
      checkedColumns.value = getKeyList(filterColumns, "label");
      checkAll.value = filterColumns.length === dynamicColumns.value.length;
      isIndeterminate.value = filterColumns.length > 0 && !checkAll.value;
      size.value = "default";
    }

    /** 列展示拖拽排序 */
    const rowDrop = (label: string) => {
      const from = dynamicColumns.value.findIndex(
        column => column.label === draggingLabel.value
      );
      const to = dynamicColumns.value.findIndex(
        column => column.label === label
      );
      if (
        from < 0 ||
        to < 0 ||
        locked(dynamicColumns.value[from]) ||
        locked(dynamicColumns.value[to])
      )
        return;
      const next = [...dynamicColumns.value];
      next.splice(to, 0, next.splice(from, 1)[0]);
      dynamicColumns.value = next;
      checkColumnList = getKeyList(next, "label");
    };

    const isFixedColumn = (label: string) => {
      const column = dynamicColumns.value.find(
        item => transformI18n(item.label) === transformI18n(label)
      );
      const fixedOption = column?.fixed;
      const left = fixedOption === "left";
      const right = fixedOption === true || fixedOption === "right";
      return { fixed: left || right, left, right };
    };

    const rendTippyProps = (content: string) => {
      // https://vue-tippy.netlify.app/props
      return {
        content,
        offset: [0, 18],
        duration: [300, 0],
        followCursor: true,
        hideOnClick: "toggle"
      };
    };

    const reference = {
      reference: () => (
        <el-button data-action="neutral" size="small" aria-label="列设置">
          <SettingIcon class="w-4 mr-1" />
          列设置
        </el-button>
      )
    };

    return () => {
      const flatten = nodes =>
        nodes.flatMap(node =>
          node.type === Fragment && Array.isArray(node.children)
            ? flatten(node.children)
            : [node]
        );
      const content = flatten(
        slots.default?.({
          size: size.value,
          dynamicColumns: dynamicColumns.value
        }) || []
      );
      const filters = content.filter(node =>
        String(node.props?.class || "").includes("list-filters")
      );
      const heading = (
        <ReListHeading title={transformI18n(props.title)}>
          {{ heading: slots.title }}
        </ReListHeading>
      );
      return (
        <>
          {props.listHeading && heading}
          <div
            {...attrs}
            class={[
              "list-card",
              "w-full",
              "px-2",
              "pb-2",
              "bg-bg_color",
              {
                "list-query-panel": filters.length > 0
              },
              "mt-2"
            ]}
          >
            {filters}
            <div class="list-card-toolbar list-card-toolbar-compact flex justify-between w-full p-4">
              {slots?.buttons ? (
                <div class="list-card-actions flex">{slots.buttons()}</div>
              ) : null}
              <div class="list-card-tools flex-ac">
                {props.tableRef?.size ? (
                  <>
                    <ExpandIcon
                      class={["w-4", iconClass.value]}
                      style={{
                        transform: isExpandAll.value ? "none" : "rotate(-90deg)"
                      }}
                      v-tippy={rendTippyProps(
                        isExpandAll.value
                          ? transformI18n($t("tableBar.pureCollapse"))
                          : transformI18n($t("tableBar.pureExpand"))
                      )}
                      onClick={() => onExpand()}
                    />
                    <el-divider direction="vertical" />
                  </>
                ) : null}
                <el-popover
                  v-slots={reference}
                  placement="bottom-start"
                  popper-style={{ padding: 0 }}
                  width="245"
                  trigger="click"
                >
                  <div class={[topClass.value]}>
                    <el-checkbox
                      class="-mr-1!"
                      label={transformI18n($t("tableBar.pureColumnDisplay"))}
                      v-model={checkAll.value}
                      indeterminate={isIndeterminate.value}
                      onChange={value => handleCheckAllChange(value)}
                    />
                    <el-button data-action="neutral" type="primary" link onClick={() => onReset()}>
                      {transformI18n($t("tableBar.pureReset"))}
                    </el-button>
                  </div>

                  <div class="pt-1.5 pl-2.75">
                    <el-scrollbar max-height="36vh">
                      <el-checkbox-group
                        ref={`GroupRef${props.tableKey}`}
                        modelValue={checkedColumns.value}
                        onChange={value => handleCheckedColumnsChange(value)}
                      >
                        <el-space
                          direction="vertical"
                          alignment="flex-start"
                          size={0}
                        >
                          {checkColumnList.map((item, index) => {
                            const { fixed, left, right } = isFixedColumn(item);
                            return (
                              <div
                                class="flex items-center"
                                draggable={
                                  !locked(
                                    dynamicColumns.value.find(
                                      column => column.label === item
                                    ) || {}
                                  )
                                }
                                onDragstart={() => (draggingLabel.value = item)}
                                onDragover={event => event.preventDefault()}
                                onDrop={() => rowDrop(item)}
                              >
                                <DragIcon
                                  class={[
                                    "drag-btn w-4 mr-2",
                                    fixed ? "cursor-no-drop!" : "cursor-grab!"
                                  ]}
                                />
                                <el-checkbox
                                  disabled={locked(
                                    dynamicColumns.value.find(
                                      column => column.label === item
                                    ) || {}
                                  )}
                                  key={index}
                                  label={item}
                                  value={item}
                                  onChange={value =>
                                    handleCheckColumnListChange(value, item)
                                  }
                                >
                                  <span
                                    title={transformI18n(item)}
                                    class="inline-block w-30 truncate hover:text-text_color_primary"
                                  >
                                    {transformI18n(item)}
                                  </span>
                                </el-checkbox>
                                <iconify-icon-offline
                                  class={[
                                    "ml-2",
                                    "size-4",
                                    "hover:text-primary",
                                    "cursor-pointer",
                                    left ? "text-primary" : ""
                                  ]}
                                  icon={left ? PinAngleFill : PinAngle}
                                  v-tippy={
                                    left
                                      ? transformI18n($t("tableBar.pureUnpin"))
                                      : transformI18n(
                                          $t("tableBar.purePinLeft")
                                        )
                                  }
                                  onClick={() =>
                                    handleToggleColumnFixed(
                                      left ? false : "left",
                                      item
                                    )
                                  }
                                />
                                <iconify-icon-offline
                                  class={[
                                    "ml-2",
                                    "size-4",
                                    "hover:text-primary",
                                    "scale-x-[-1]",
                                    "cursor-pointer",
                                    right ? "text-primary" : ""
                                  ]}
                                  icon={right ? PinAngleFill : PinAngle}
                                  v-tippy={
                                    right
                                      ? transformI18n($t("tableBar.pureUnpin"))
                                      : transformI18n(
                                          $t("tableBar.purePinRight")
                                        )
                                  }
                                  onClick={() =>
                                    handleToggleColumnFixed(
                                      right ? false : "right",
                                      item
                                    )
                                  }
                                />
                              </div>
                            );
                          })}
                        </el-space>
                      </el-checkbox-group>
                    </el-scrollbar>
                  </div>
                </el-popover>
              </div>
            </div>
            {content.filter(node => !filters.includes(node))}
          </div>
        </>
      );
    };
  }
});
