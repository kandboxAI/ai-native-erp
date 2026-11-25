import {
  cloneVNode,
  computed,
  defineComponent,
  Fragment,
  h,
  inject,
  nextTick,
  ref,
  resolveComponent,
  useAttrs,
  type VNode
} from "vue";
import {
  ElButton,
  ElCheckbox,
  ElDropdown,
  ElDropdownItem,
  ElDropdownMenu,
  ElPopover,
  ElTable,
  ElMessage
} from "element-plus";
import { useRoute } from "vue-router";
import { transformI18n } from "@/plugins/i18n";
import { Setting } from "@element-plus/icons-vue";
import ListRowActions from "./rowActions";
import ReListPagination from "../ReListPagination";
import { listColumnWidth } from "@/utils/listColumnWidth";
import {
  clearListPreference,
  columnKeys,
  getListQuery,
  mergeColumnPreferences,
  readListPreference,
  saveListPreference,
  setListSort,
  sortListTree,
  type ColumnPreference
} from "@/utils/listState";

type Column = {
  key: string;
  label: string;
  node?: VNode;
  column?: any;
  hidden?: boolean;
  locked?: boolean;
  fixed?: any;
};

export default defineComponent({
  name: "ReListTable",
  inheritAttrs: false,
  props: {
    engine: { type: String, default: "element" },
    listKey: { type: String, default: "default" },
    listTitle: { type: String, default: "" },
    listHeading: { type: Boolean, default: true },
    listCompact: { type: Boolean, default: false },
    listWidthMode: { type: String, default: "balanced" },
    listRefresh: Function,
    listControls: { type: Boolean, default: true },
    listLocal: { type: Boolean, default: false },
    listLocalData: Array,
    listPage: { type: Number, default: 1 },
    listPageSize: { type: Number, default: 20 }
  },
  setup(props, { slots, expose }) {
    const attrs = useAttrs();
    const route = useRoute();
    const table = ref<any>();
    const container = ref<HTMLElement>();
    const inheritedRefresh = inject<() => unknown>("list-refresh", undefined);
    const managed = inject<boolean>("list-columns-managed", false);
    const saved = ref<ColumnPreference[]>();
    const size = ref<"large" | "default" | "small">("default");
    const busy = ref(false);
    const dragging = ref("");
    const localSort = ref<{ prop?: string; order?: string }>({});
    const settingsVersion = ref(0);
    let loadedKey = "";
    let currentColumns: Column[] = [];
    const actionWidths = ref<Record<string, number>>({});
    const actionMeasurements = new Map<string, Map<unknown, number>>();
    let measuredData: unknown;
    let actionVersion = 0;
    let measurementPending = false;
    function resetActionWidths() {
      actionVersion++;
      actionMeasurements.clear();
      actionWidths.value = {};
    }
    function actionSlot(content: () => any, key: string, row: unknown) {
      const version = actionVersion;
      const rowKey = attrs.rowKey || attrs["row-key"];
      const record = row as Record<string, unknown> | undefined;
      const measurementKey =
        typeof rowKey === "function"
          ? rowKey(row)
          : typeof rowKey === "string"
            ? (record?.[rowKey] ?? row)
            : (record?.id ?? row);
      return h(
        ListRowActions,
        {
          onMeasure: (width: number) => {
            if (version !== actionVersion) return;
            const rows = actionMeasurements.get(key) || new Map();
            if (rows.get(measurementKey) === width) return;
            rows.set(measurementKey, width);
            actionMeasurements.set(key, rows);
            if (measurementPending) return;
            measurementPending = true;
            nextTick(() => {
              measurementPending = false;
              const widths = Object.fromEntries(
                [...actionMeasurements].map(([key, rows]) => [
                  key,
                  Math.max(
                    80,
                    Math.ceil((Math.max(...rows.values()) + 24) / 8) * 8
                  )
                ])
              );
              if (JSON.stringify(widths) === JSON.stringify(actionWidths.value))
                return;
              actionWidths.value = widths;
              nextTick(() => table.value?.doLayout?.());
            });
          }
        },
        { default: content }
      );
    }
    const identity = computed(
      () =>
        `${route.path}:${String(route.meta.entity || route.meta.report || "")}:${props.listKey}`
    );
    const query = computed(() => getListQuery((attrs.data as any[]) || []));
    const refresh = () => (props.listRefresh || inheritedRefresh)?.();
    const canRefresh = () => !!(props.listRefresh || inheritedRefresh);
    expose(
      new Proxy(
        {},
        {
          has: (_, key) => !!table.value && key in table.value,
          get: (_, key) =>
            typeof table.value?.[key] === "function"
              ? table.value[key].bind(table.value)
              : table.value?.[key]
        }
      )
    );

    function persist(columns = currentColumns) {
      saved.value = columns.map(({ key, hidden, fixed }) => ({
        key,
        hidden,
        fixed
      }));
      saveListPreference(identity.value, {
        version: 1,
        columns: saved.value,
        size: size.value
      });
      settingsVersion.value++;
      nextTick(() => table.value?.doLayout?.());
    }
    function update(column: Column, changes: Partial<Column>) {
      if (column.locked) return;
      persist(
        currentColumns.map(item =>
          item.key === column.key ? { ...item, ...changes } : item
        )
      );
    }
    function drop(key: string) {
      const from = currentColumns.findIndex(
        column => column.key === dragging.value
      );
      const to = currentColumns.findIndex(column => column.key === key);
      if (
        from < 0 ||
        to < 0 ||
        currentColumns[from].locked ||
        currentColumns[to].locked
      )
        return;
      const columns = [...currentColumns];
      columns.splice(to, 0, columns.splice(from, 1)[0]);
      persist(columns);
    }
    async function onSort(change: { prop: string; order: string }) {
      const listener = attrs.onSortChange as
        ((value: any) => unknown) | undefined;
      if (props.listLocal || props.listLocalData) {
        localSort.value = change;
        listener?.(change);
        return;
      }
      if (!query.value) {
        listener?.(change);
        return;
      }
      busy.value = true;
      try {
        setListSort(query.value, change.prop, change.order);
        await refresh();
      } catch (error) {
        ElMessage.error((error as Error)?.message || "排序加载失败，请重试");
      } finally {
        busy.value = false;
      }
    }
    function flatten(nodes: VNode[]): VNode[] {
      return nodes.flatMap(node =>
        node.type === Fragment && Array.isArray(node.children)
          ? flatten(node.children as VNode[])
          : [node]
      );
    }
    function getColumns(nodes: VNode[]): Column[] {
      const columnNodes = nodes.filter(
        node =>
          (node.type as any)?.name === "ElTableColumn" ||
          (node.type as any)?.__name === "ElTableColumn"
      );
      const keys = columnKeys(
        columnNodes.map(({ props: column }) => ({
          prop: column?.prop || column?.property,
          type: column?.type,
          label: column?.label
        }))
      );
      return columnNodes.map((node, index) => {
        const p = node.props || {};
        const label = String(p.label || "");
        const field = p.prop || p.property;
        return {
          key: keys[index],
          label:
            label ||
            (p.type === "selection"
              ? "选择"
              : p.type === "index"
                ? "序号"
                : "列"),
          node,
          hidden: p.listHidden === true || p["list-hidden"] === true,
          fixed: p.fixed,
          locked:
            ["selection", "index", "expand"].includes(p.type) ||
            /操作|办理|录入/.test(label) ||
            (!field && !!p.fixed)
        };
      });
    }
    function sortable(field: string, existing: any) {
      if (existing === false) return false;
      if (props.listLocal || props.listLocalData)
        return field ? "custom" : existing;
      if (query.value && canRefresh())
        return query.value.fields.includes(field) ? "custom" : false;
      return existing;
    }
    function columnHeader({ column }: { column: { label?: string } }) {
      const label = String(column.label || "");
      return [h("span", { class: "list-column-label", title: label }, label)];
    }
    return () => {
      void settingsVersion.value;
      if (loadedKey !== identity.value) {
        loadedKey = identity.value;
        const preference = readListPreference(loadedKey);
        saved.value = preference?.columns;
        size.value = preference?.size || "default";
        localSort.value = {};
        resetActionWidths();
      }
      if (measuredData !== attrs.data) {
        measuredData = attrs.data;
        resetActionWidths();
      }
      const nodes =
        props.engine === "pure" ? [] : flatten(slots.default?.() || []);
      const pureColumns = ((attrs.columns as any[]) || []).filter(
        column => !(typeof column.hide === "function" && column.hide())
      );
      const pureKeys = columnKeys(pureColumns);
      const source: Column[] =
        props.engine === "pure"
          ? pureColumns.map((column, index) => ({
              key: pureKeys[index],
              label: String(column.label || "列"),
              column,
              hidden:
                typeof column.hide === "function"
                  ? column.hide()
                  : !!column.hide,
              fixed: column.fixed,
              locked: !!column.type || column.slot === "operation"
            }))
          : getColumns(nodes);
      currentColumns = managed
        ? source
        : mergeColumnPreferences(source, saved.value);
      const visible = currentColumns.filter(
        column => !column.hidden || column.locked
      );
      const isAction = (column: Column) =>
        props.listControls && column.label === "操作";
      const balancedWidths =
        props.listWidthMode === "balanced" &&
        props.listControls &&
        attrs.fit !== false &&
        attrs.fit !== "false" &&
        (attrs.tableLayout ?? attrs["table-layout"]) !== "auto";
      const columnNodes = visible
        .filter(column => column.node)
        .map(column => {
          const action = isAction(column);
          let node = cloneVNode(column.node!, {
            key: column.key,
            fixed: column.fixed,
            ...(balancedWidths
              ? listColumnWidth(
                  column.node?.props || {},
                  column.locked || isAction(column)
                )
              : {}),
            ...(action
              ? {
                  showOverflowTooltip: false,
                  className: [
                    column.node?.props?.className ||
                      column.node?.props?.["class-name"],
                    "list-actions-column"
                  ]
                    .filter(Boolean)
                    .join(" "),
                  width:
                    actionWidths.value[column.key] ||
                    Math.min(Number(column.node?.props?.width) || 160, 180),
                  minWidth: actionWidths.value[column.key] || 80
                }
              : {}),
            sortable: sortable(
              String(
                column.node?.props?.prop || column.node?.props?.property || ""
              ),
              column.node?.props?.sortable
            )
          });
          const children = (column.node!.children || {}) as any;
          const columnSlots = { ...children };
          let slotsChanged = false;
          if (action && children.default) {
            columnSlots.default = (scope: any) => [
              actionSlot(() => children.default(scope), column.key, scope.row)
            ];
            slotsChanged = true;
          }
          if (
            (props.listControls || managed) &&
            !["selection", "index", "expand"].includes(
              column.node?.props?.type
            ) &&
            !children.header &&
            !column.node?.props?.renderHeader &&
            !column.node?.props?.["render-header"]
          ) {
            columnSlots.header = columnHeader;
            slotsChanged = true;
          }
          if (slotsChanged) node = h(node, null, columnSlots);
          return node;
        });
      const passthrough = nodes.filter(
        node => !source.some(column => column.node === node)
      );
      const tableAttrs: any = {
        ...attrs,
        ref: table,
        class: [
          "list-table",
          { "list-table-standard": props.listControls || managed },
          attrs.class
        ],
        onSortChange: onSort
      };
      const pagination =
        props.engine === "pure" &&
        attrs.pagination &&
        typeof attrs.pagination === "object"
          ? (attrs.pagination as Record<string, any>)
          : undefined;
      // Pure 在挂载时根据 currentPage/pageSize 决定是否创建内置分页，total=0 无法关闭。
      // 从首次挂载起传入空配置，真实分页状态仅由外部统一分页组件维护。
      if (props.engine === "pure") tableAttrs.pagination = {};
      if (props.listLocal || props.listLocalData) {
        const data = props.listLocalData || (attrs.data as any[]) || [];
        const sorted = sortListTree(
          data,
          localSort.value.prop,
          localSort.value.order,
          ((attrs.treeProps || attrs["tree-props"]) as any)?.children ||
            "children"
        );
        tableAttrs.data = props.listLocalData
          ? sorted.slice(
              (props.listPage - 1) * props.listPageSize,
              props.listPage * props.listPageSize
            )
          : sorted;
      }
      if (!managed && props.listControls) tableAttrs.size = size.value;
      if (props.listControls || managed) {
        tableAttrs.stripe = false;
        tableAttrs.border = false;
      }
      const tableSlots = { ...slots };
      const inheritedTooltip =
        attrs.showOverflowTooltip ?? attrs["show-overflow-tooltip"];
      const separateTooltips =
        props.engine === "pure" && visible.some(isAction);
      if (separateTooltips) {
        // PureTable falls back to its table setting even when a column explicitly says false.
        tableAttrs.showOverflowTooltip = false;
        delete tableAttrs["show-overflow-tooltip"];
      }
      if (props.engine === "pure")
        tableAttrs.columns = visible.map(item => {
          const action = isAction(item);
          if (action && item.column.slot && slots[item.column.slot]) {
            const slot = slots[item.column.slot]!;
            tableSlots[item.column.slot] = scope => [
              actionSlot(() => slot(scope), item.key, scope.row)
            ];
          }
          return {
            ...item.column,
            ...(balancedWidths
              ? listColumnWidth(item.column, item.locked || action)
              : {}),
            ...((props.listControls || managed) &&
            !["selection", "index", "expand"].includes(item.column.type) &&
            !item.column.headerRenderer &&
            !item.column.headerSlot &&
            !item.column.renderHeader
              ? { headerRenderer: columnHeader }
              : {}),
            ...(separateTooltips && !action
              ? {
                  showOverflowTooltip:
                    item.column.showOverflowTooltip ??
                    (inheritedTooltip === "" ? true : inheritedTooltip)
                }
              : {}),
            ...(action
              ? {
                  showOverflowTooltip: false,
                  className: [item.column.className, "list-actions-column"]
                    .filter(Boolean)
                    .join(" "),
                  width:
                    actionWidths.value[item.key] ||
                    Math.min(Number(item.column.width) || 160, 180),
                  minWidth: actionWidths.value[item.key] || 80,
                  ...(item.column.cellRenderer
                    ? {
                        cellRenderer: (scope: any) =>
                          actionSlot(
                            () => item.column.cellRenderer(scope),
                            item.key,
                            scope.row
                          )
                      }
                    : {})
                }
              : {}),
            align: item.column?.align || "left",
            headerAlign:
              item.column?.headerAlign || item.column?.align || "left",
            hide: false,
            fixed: item.fixed,
            sortable: sortable(item.column?.prop, item.column?.sortable)
          };
        });
      const controls = props.listControls && !managed;
      const engine =
        props.engine === "pure" ? resolveComponent("pure-table") : ElTable;
      const renderTable = () =>
        h(
          engine as any,
          tableAttrs,
          props.engine === "pure"
            ? tableSlots
            : {
                ...slots,
                default: () =>
                  source.length ? [...columnNodes, ...passthrough] : nodes
              }
        );
      return (
        <section
          ref={container}
          class={[
            "list-table-panel",
            {
              "list-table-managed": managed,
              "list-table-compact": props.listCompact
            }
          ]}
          aria-busy={busy.value}
        >
          {controls && (
            <div
              class={[
                "list-card-toolbar",
                "list-table-tools",
                {
                  "list-card-toolbar-compact":
                    props.listCompact || !props.listHeading
                }
              ]}
            >
              {!props.listCompact && props.listHeading && (
                <div class="list-card-title">
                  <h2>
                    {slots["list-title"]?.() ||
                      props.listTitle ||
                      transformI18n(String(route.meta.title || "数据列表"))}
                  </h2>
                  {slots["list-description"] && (
                    <div class="list-heading-content">
                      {slots["list-description"]()}
                    </div>
                  )}
                </div>
              )}
              <div class="list-card-actions">
                {slots["list-actions"]?.()}
                {props.listCompact && !slots["list-actions"] && (
                  <span class="list-table-tools-label">
                    本页 {(attrs.data as any[])?.length || 0} 条
                  </span>
                )}
              </div>
              <div class="list-card-tools list-table-tools-actions">
                <ElPopover width={286} trigger="click" placement="bottom-end">
                  {{
                    reference: () => (
                      <ElButton data-action="neutral"
                        class="list-tool-columns"
                        size="small"
                        icon={Setting}
                      >
                        列设置
                      </ElButton>
                    ),
                    default: () => (
                      <div class="list-column-settings">
                        <header>
                          <strong>列设置</strong>
                          <span>拖动调整顺序</span>
                        </header>
                        <div class="list-column-settings-items">
                          {currentColumns.map(column => (
                            <div
                              key={column.key}
                              class="list-column-setting"
                              draggable={!column.locked}
                              onDragstart={() => (dragging.value = column.key)}
                              onDragover={event => event.preventDefault()}
                              onDrop={() => drop(column.key)}
                            >
                              <span class="list-column-drag" aria-hidden="true">
                                ⠿
                              </span>
                              <ElCheckbox
                                modelValue={!column.hidden || column.locked}
                                disabled={column.locked}
                                onChange={value =>
                                  update(column, { hidden: !value })
                                }
                              >
                                {column.label}
                              </ElCheckbox>
                              {!column.locked && (
                                <ElDropdown
                                  onCommand={value =>
                                    update(column, {
                                      fixed: value === "none" ? false : value
                                    })
                                  }
                                >
                                  {{
                                    default: () => (
                                      <ElButton data-action="neutral" link size="small">
                                        {column.fixed === "left"
                                          ? "固定左侧"
                                          : column.fixed === "right" ||
                                              column.fixed === true
                                            ? "固定右侧"
                                            : "固定"}
                                      </ElButton>
                                    ),
                                    dropdown: () => (
                                      <ElDropdownMenu>
                                        <ElDropdownItem command="left">
                                          固定左侧
                                        </ElDropdownItem>
                                        <ElDropdownItem command="right">
                                          固定右侧
                                        </ElDropdownItem>
                                        <ElDropdownItem command="none">
                                          取消固定
                                        </ElDropdownItem>
                                      </ElDropdownMenu>
                                    )
                                  }}
                                </ElDropdown>
                              )}
                            </div>
                          ))}
                        </div>
                        <footer>
                          <ElButton data-action="neutral"
                            size="small"
                            onClick={() => {
                              clearListPreference(identity.value);
                              saved.value = undefined;
                              size.value = "default";
                              settingsVersion.value++;
                            }}
                          >
                            恢复默认
                          </ElButton>
                          <span>设置自动保存</span>
                        </footer>
                      </div>
                    )
                  }}
                </ElPopover>
              </div>
            </div>
          )}
          {controls ? (
            <div class="list-card-body">{renderTable()}</div>
          ) : (
            renderTable()
          )}
          {pagination && !slots["list-pagination"] && (
            <div class="list-card-pagination">
              <ReListPagination
                currentPage={pagination.currentPage || 1}
                pageSize={pagination.pageSize || 20}
                total={pagination.total || 0}
                fixedPageSize={!attrs.onPageSizeChange}
                disabled={!!attrs.loading}
                {...{
                  "onUpdate:currentPage": (page: number) => {
                    pagination.currentPage = page;
                  },
                  "onUpdate:pageSize": (size: number) => {
                    pagination.pageSize = size;
                  },
                  onCurrentChange: attrs.onPageCurrentChange,
                  onSizeChange: attrs.onPageSizeChange
                }}
              />
            </div>
          )}
          {slots["list-pagination"] && (
            <div class="list-card-pagination">{slots["list-pagination"]()}</div>
          )}
        </section>
      );
    };
  }
});
