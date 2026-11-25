import dayjs from "dayjs";
import Detail from "./detail.vue";
import { message } from "@/utils/message";
import { addDialog } from "@/components/ReDialog";
import type { PaginationProps } from "@pureadmin/table";
import { type Ref, reactive, ref, onMounted, toRaw } from "vue";
import { useCopyToClipboard } from "@pureadmin/utils";
import { getHttpErrorMessage } from "@/utils/http";
import { getSystemLogsDetail, getSystemLogsList } from "@/api/system";
import Info from "~icons/ri/question-line";

export function useRole(tableRef: Ref) {
  const form = reactive({
    module: "",
    requestTime: ""
  });
  const dataList = ref([]);
  const loading = ref(true);
  const selectedNum = ref(0);
  const { copied, update } = useCopyToClipboard();

  const pagination = reactive<PaginationProps>({
    total: 0,
    pageSize: 20,
    currentPage: 1,
    background: true
  });

  const columns: TableColumnList = [
    {
      label: "勾选列",
      type: "selection",
      fixed: "left",
      reserveSelection: true
    },
    {
      label: "所属模块",
      prop: "module",
      minWidth: 120
    },
    {
      headerRenderer: () => (
        <span class="flex-c">
          请求接口
          <iconify-icon-offline
            icon={Info}
            class="ml-1 cursor-help"
            v-tippy={{
              content: "双击下面请求接口进行拷贝"
            }}
          />
        </span>
      ),
      prop: "url",
      minWidth: 220
    },
    {
      label: "请求方法",
      prop: "method",
      minWidth: 100
    },
    {
      label: "IP 地址",
      prop: "ip",
      minWidth: 140
    },
    {
      label: "操作人员",
      prop: "username",
      minWidth: 140
    },
    {
      label: "请求时间",
      prop: "requestTime",
      minWidth: 180,
      formatter: ({ requestTime }) =>
        requestTime ? dayjs(requestTime).format("YYYY-MM-DD HH:mm:ss") : "—"
    },
    {
      label: "操作",
      fixed: "right",
      slot: "operation"
    }
  ];

  function handleSizeChange(val: number) {
    pagination.pageSize = val;
    pagination.currentPage = 1;
    onSearch();
  }

  function handleCurrentChange(val: number) {
    pagination.currentPage = val;
    onSearch();
  }

  function handleSelectionChange(val) {
    selectedNum.value = val.length;
    tableRef.value.setAdaptive();
  }

  function onSelectionCancel() {
    selectedNum.value = 0;
    tableRef.value.getTableRef().clearSelection();
  }

  function handleCellDblclick({ url }, { property }) {
    if (property !== "url") return;
    update(url);
    copied.value
      ? message(`${url} 已拷贝`, { type: "success" })
      : message("拷贝失败", { type: "warning" });
  }

  async function onDetail(row) {
    try {
      const detail = await getSystemLogsDetail({ id: row.id });
      addDialog({
        title: "系统日志详情",
        fullscreen: true,
        hideFooter: true,
        contentRenderer: () => Detail,
        props: {
          data: [detail]
        }
      });
    } catch (error) {
      message(getHttpErrorMessage(error, "查询日志详情失败"), {
        type: "error"
      });
    }
  }

  async function onSearch() {
    loading.value = true;
    try {
      const {
        code,
        data,
        message: apiMessage
      } = await getSystemLogsList({
        ...toRaw(form),
        currentPage: pagination.currentPage,
        pageSize: pagination.pageSize
      });
      if (code === 0) {
        dataList.value = data.list;
        pagination.total = data.total;
        pagination.pageSize = data.pageSize;
        pagination.currentPage = data.currentPage;
      } else {
        message(apiMessage || "查询系统日志失败", { type: "error" });
      }
    } catch (error) {
      message(getHttpErrorMessage(error, "查询系统日志失败"), {
        type: "error"
      });
    } finally {
      loading.value = false;
    }
  }

  const resetForm = formEl => {
    if (!formEl) return;
    formEl.resetFields();
    pagination.currentPage = 1;
    onSearch();
  };

  onMounted(() => {
    onSearch();
  });

  return {
    form,
    loading,
    columns,
    dataList,
    pagination,
    selectedNum,
    onSearch,
    onDetail,
    resetForm,
    handleSizeChange,
    onSelectionCancel,
    handleCellDblclick,
    handleCurrentChange,
    handleSelectionChange
  };
}
