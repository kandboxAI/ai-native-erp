import dayjs from "dayjs";
import { message } from "@/utils/message";
import { getHttpErrorMessage } from "@/utils/http";
import { getOnlineLogsList, kickOnlineUser } from "@/api/system";
import { reactive, ref, onMounted, toRaw } from "vue";
import type { PaginationProps } from "@pureadmin/table";

export function useRole() {
  const form = reactive({
    username: ""
  });
  const dataList = ref([]);
  const loading = ref(true);
  const pagination = reactive<PaginationProps>({
    total: 0,
    pageSize: 20,
    currentPage: 1,
    background: true
  });
  const columns: TableColumnList = [
    {
      label: "用户名",
      prop: "username",
      minWidth: 120
    },
    {
      label: "邮箱",
      prop: "email",
      minWidth: 160
    },
    {
      label: "角色",
      prop: "roleNos",
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
      label: "最近活跃",
      prop: "loginTime",
      minWidth: 180,
      formatter: ({ loginTime }) =>
        loginTime ? dayjs(loginTime).format("YYYY-MM-DD HH:mm:ss") : "—"
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

  function handleSelectionChange() {}

  async function handleOffline(row) {
    if (!row?.auth_user_id) {
      message("缺少用户 ID，无法强制下线", { type: "warning" });
      return;
    }
    try {
      await kickOnlineUser(row.auth_user_id);
      message(`${row.username} 已被强制下线`, { type: "success" });
      await onSearch();
    } catch (error) {
      message(getHttpErrorMessage(error, "强制下线失败"), { type: "error" });
    }
  }

  async function onSearch() {
    loading.value = true;
    try {
      const {
        code,
        data,
        message: apiMessage
      } = await getOnlineLogsList({
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
        message(apiMessage || "查询在线用户失败", { type: "error" });
      }
    } catch (error) {
      message(getHttpErrorMessage(error, "查询在线用户失败"), {
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
    onSearch,
    resetForm,
    handleOffline,
    handleSizeChange,
    handleCurrentChange,
    handleSelectionChange
  };
}
