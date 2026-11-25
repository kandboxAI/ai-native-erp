import { nextTick, onBeforeUnmount, reactive, ref, watch, type Ref } from "vue";
import type { FormInstance } from "element-plus";
import type {
  MesOption,
  MesProcessTemplate,
} from "@plugins/mes/web/src/api/mes";
import { actionMessage, message } from "@/utils/message";
import { getHttpErrorMessage } from "@/utils/http";
import { routeOperations } from "./routeDefinitions";
import { operation, type OperationForm } from "./operationDefinitions";
import type { OperationCatalog } from "./operationCatalog";

export function useWorkOrderOperations(
  form: OperationForm,
  options: {
    visible: Ref<boolean>;
    configurationLocked: Ref<boolean>;
    saving: Ref<boolean>;
    manage: Ref<boolean>;
    canSaveRoutes: Ref<boolean>;
    unit: Ref<string>;
    productOption: Ref<MesOption | undefined>;
    formRef: Ref<FormInstance | undefined>;
    source: OperationCatalog;
  },
) {
  const {
    visible,
    configurationLocked,
    saving,
    manage,
    canSaveRoutes,
    unit,
    productOption,
    formRef,
    source,
  } = options;
  const templateChoices = ref<MesProcessTemplate[]>([]);
  const templateId = ref("");
  const templateLoading = ref(false);
  const templateError = ref("");
  const templatesLoaded = ref(false);
  const routeVisible = ref(false),
    routeSaving = ref(false);
  const routeForm = reactive({
    template_no: "",
    template_name: "",
    scope: "product",
  });

  let editorSession = 0,
    applyingTemplate = false,
    templateRequest = 0,
    initializing = false,
    disposed = false,
    wasVisible = false;
  const activeOperationKey = ref<number | undefined>(form.operations[0]?.key);
  const operationList = ref<HTMLElement>();
  watch(
    visible,
    (value) => {
      wasVisible = value;
      ++editorSession;
      ++templateRequest;
      routeVisible.value = false;
      templateLoading.value = false;
      if (!value) return;
      initializing = true;
      templateId.value = form.process_template_id || "";
      templateChoices.value = [];
      templateError.value = "";
      templatesLoaded.value = false;
      activeOperationKey.value = form.operations[0]?.key;
      nextTick(() => {
        initializing = false;
        if (!disposed && visible.value && !configurationLocked.value)
          searchTemplates();
      });
    },
    { immediate: true, flush: "post" },
  );
  onBeforeUnmount(() => {
    disposed = true;
    ++templateRequest;
    ++editorSession;
  });
  function clearTemplate() {
    form.process_template_id = null;
    form.process_template_version_snapshot = null;
    templateId.value = "";
    templateChoices.value = [];
    ++templateRequest;
    templateLoading.value = false;
    templateError.value = "";
    templatesLoaded.value = false;
  }
  watch(
    () => form.org_id,
    () => {
      if (initializing || !visible.value || !wasVisible) return;
      clearTemplate();
      form.operations.forEach((row) => {
        row.assigned_user_id = "";
        row.assigned_user_name = "";
      });
      if (visible.value) searchTemplates();
    },
  );
  watch(
    () => form.product_item_id,
    (value, previous) => {
      if (initializing || applyingTemplate || !visible.value || !wasVisible)
        return;
      const general =
        !previous &&
        form.process_template_id &&
        templateChoices.value.some(
          (item) =>
            item.id === form.process_template_id && !item.product_item_id,
        );
      if (!general) clearTemplate();
      if (visible.value) searchTemplates();
    },
  );
  async function searchTemplates(keyword = "") {
    const current = ++templateRequest;
    templateError.value = "";
    if (!form.org_id || configurationLocked.value) {
      templateLoading.value = false;
      return;
    }
    templateLoading.value = true;
    const org = form.org_id,
      product = form.product_item_id;
    try {
      const result = await source.loadTemplates({
        keyword,
        org_id: org,
        product_item_id: product || undefined,
        is_active: true,
        page_size: 50,
        action: manage.value ? "manage" : "create",
      });
      if (
        current === templateRequest &&
        org === form.org_id &&
        product === form.product_item_id
      ) {
        templateChoices.value = result;
        templatesLoaded.value = true;
      }
    } catch (cause: any) {
      if (current === templateRequest) {
        templateChoices.value = [];
        templateError.value = getHttpErrorMessage(
          cause,
          "工艺路线加载失败，请重试",
        );
      }
    } finally {
      if (current === templateRequest) templateLoading.value = false;
    }
  }
  async function applyTemplate() {
    if (saving.value || configurationLocked.value) return;
    const template = templateChoices.value.find(
      (row) => row.id === templateId.value,
    );
    if (
      !template ||
      template.org_id !== form.org_id ||
      template.is_product_active === false ||
      (template.product_item_id &&
        form.product_item_id &&
        template.product_item_id !== form.product_item_id)
    )
      return;
    if (
      template.product_item_id &&
      !form.product_item_id &&
      !template.product_option
    ) {
      actionMessage("该路线的产品信息未返回，请刷新路线列表后重试", "warning");
      return;
    }
    applyingTemplate = true;
    ++templateRequest;
    templateLoading.value = false;
    if (template.product_item_id && !form.product_item_id) {
      form.product_item_id = template.product_item_id;
      productOption.value = template.product_option;
      unit.value = template.product_option?.unit || "";
    }
    templateChoices.value = templateChoices.value.filter(
      (item) =>
        !form.product_item_id ||
        !item.product_item_id ||
        item.product_item_id === form.product_item_id,
    );
    form.operations = template.operations.map((row, index) => ({
      ...operation(index + 1),
      ...row,
      assigned_user_id: "",
      assigned_user_name: "",
      work_center_name: row.work_center_name || "",
      workstation_name: row.workstation_name || "",
      operation_description: row.operation_description || "",
    }));
    form.process_template_id = template.id || null;
    form.process_template_version_snapshot = template.version_no || null;
    activeOperationKey.value = form.operations[0]?.key;
    formRef.value?.clearValidate();
    await nextTick();
    applyingTemplate = false;
  }

  function openSaveRoute() {
    if (
      saving.value ||
      routeSaving.value ||
      configurationLocked.value ||
      !canSaveRoutes.value
    )
      return;
    try {
      if (!form.org_id) throw new Error("请先选择组织");
      routeOperations(form.operations);
      Object.assign(routeForm, {
        template_no: "",
        template_name: "",
        scope: form.product_item_id ? "product" : "general",
      });
      routeVisible.value = true;
    } catch (cause) {
      message(getHttpErrorMessage(cause, "请先补全工序"), { type: "warning" });
    }
  }
  async function saveCurrentRoute() {
    if (
      routeSaving.value ||
      !routeVisible.value ||
      configurationLocked.value ||
      !canSaveRoutes.value
    )
      return;
    const session = editorSession,
      org = form.org_id,
      product = form.product_item_id;
    routeSaving.value = true;
    try {
      if (
        !org ||
        !routeForm.template_no.trim() ||
        !routeForm.template_name.trim()
      )
        throw new Error("请填写路线编号和名称");
      if (routeForm.scope === "product" && !product)
        throw new Error("请先选择生产产品，或保存为组织通用路线");
      const payload: MesProcessTemplate = {
        org_id: org,
        template_no: routeForm.template_no.trim(),
        template_name: routeForm.template_name.trim(),
        product_item_id: routeForm.scope === "product" ? product : null,
        is_active: true,
        operations: routeOperations(form.operations),
      };
      const result = await source.saveTemplate(payload);
      if (
        session !== editorSession ||
        !visible.value ||
        org !== form.org_id ||
        product !== form.product_item_id ||
        disposed
      )
        return;
      ++templateRequest;
      templateLoading.value = false;
      const item = {
        ...payload,
        id: result.id,
        version_no: result.version_no,
        product_option: payload.product_item_id
          ? productOption.value
          : undefined,
      };
      templateChoices.value = [
        item,
        ...templateChoices.value.filter((row) => row.id !== item.id),
      ];
      templateId.value = item.id;
      form.process_template_id = item.id;
      form.process_template_version_snapshot = item.version_no;
      routeVisible.value = false;
      message("工艺路线已保存；当前工序数量和派工保持原样", {
        type: "success",
      });
    } catch (cause) {
      if (session === editorSession)
        actionMessage(getHttpErrorMessage(cause, "工艺路线保存失败，请重试"));
    } finally {
      routeSaving.value = false;
    }
  }
  function move(index: number, delta: number) {
    if (
      saving.value ||
      configurationLocked.value ||
      index < 0 ||
      index >= form.operations.length ||
      index + delta < 0 ||
      index + delta >= form.operations.length
    )
      return;
    const [row] = form.operations.splice(index, 1);
    form.operations.splice(index + delta, 0, row);
    orderChanged();
  }
  function orderChanged() {
    // Validation paths use array indexes; discard messages belonging to the old order.
    nextTick(() =>
      formRef.value?.clearValidate(
        form.operations.flatMap((_, index) => [
          `operations.${index}.operation_no`,
          `operations.${index}.operation_name`,
        ]),
      ),
    );
  }
  async function revealOperation(key: number) {
    activeOperationKey.value = key;
    await nextTick();
    operationList.value
      ?.querySelector<HTMLElement>(`[data-operation-key="${key}"]`)
      ?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }
  function removeOperation(index: number) {
    if (saving.value || configurationLocked.value) return;
    const [removed] = form.operations.splice(index, 1);
    if (activeOperationKey.value === removed.key) {
      const next = form.operations[Math.min(index, form.operations.length - 1)];
      if (next) revealOperation(next.key);
      else activeOperationKey.value = undefined;
    }
    orderChanged();
  }
  function addOperation() {
    if (
      saving.value ||
      configurationLocked.value ||
      form.operations.length >= 100
    )
      return;
    const existing = new Set(form.operations.map((row) => row.operation_no));
    let number = 10;
    while (existing.has(String(number))) number += 10;
    const row = operation(1);
    row.operation_no = String(number);
    form.operations.push(row);
    revealOperation(row.key);
  }

  return {
    form,
    visible,
    configurationLocked,
    saving,
    manage,
    canSaveRoutes,
    unit,
    productOption,
    formRef,
    source,
    templateChoices,
    templateId,
    templateLoading,
    templateError,
    templatesLoaded,
    routeVisible,
    routeSaving,
    routeForm,
    activeOperationKey,
    operationList,
    searchTemplates,
    applyTemplate,
    openSaveRoute,
    saveCurrentRoute,
    move,
    orderChanged,
    revealOperation,
    removeOperation,
    addOperation,
  };
}
