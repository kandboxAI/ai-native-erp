import dayjs from "dayjs";
import { message } from "@/utils/message";
import { getHttpErrorMessage } from "@/utils/http";
import { getLoginLogsList } from "@/api/system";
import { usePublicHooks } from "@/views/system/hooks";
import type { PaginationProps } from "@pureadmin/table";
import { type Ref, reactive, ref, onMounted, toRaw } from "vue";

export function useRole(tableRef: Ref) {
  const form = reactive({
    username: "",
    status: "",
    loginTime: ""
  });
  const dataList = ref([]);
  const loading = ref(true);
  const selectedNum = ref(0);
  const { tagStyle } = usePublicHooks();

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
      label: "用户名",
      prop: "username",
      minWidth: 120
    },
    {
      label: "登录账号",
      prop: "loginName",
      minWidth: 160
    },
    {
      label: "登录 IP",
      prop: "ip",
      minWidth: 140
    },
    {
      label: "操作系统",
      prop: "system",
      minWidth: 100
    },
    {
      label: "浏览器类型",
      prop: "browser",
      minWidth: 100
    },
    {
      label: "登录状态",
      prop: "status",
      minWidth: 100,
      cellRenderer: ({ row, props }) => (
        <el-tag size={props.size} style={tagStyle.value(row.status)}>
          {row.status === 1 ? "成功" : "失败"}
        </el-tag>
      )
    },
    {
      label: "登录行为",
      prop: "behavior",
      minWidth: 140
    },
    {
      label: "登录时间",
      prop: "loginTime",
      minWidth: 180,
      formatter: ({ loginTime }) =>
        loginTime ? dayjs(loginTime).format("YYYY-MM-DD HH:mm:ss") : "—"
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

  async function onSearch() {
    loading.value = true;
    try {
      const {
        code,
        data,
        message: apiMessage
      } = await getLoginLogsList({
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
        message(apiMessage || "查询登录日志失败", { type: "error" });
      }
    } catch (error) {
      message(getHttpErrorMessage(error, "查询登录日志失败"), {
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
    resetForm,
    handleSizeChange,
    onSelectionCancel,
    handleCurrentChange,
    handleSelectionChange
  };
}
