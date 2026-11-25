import type { MenuTypeCode, OpenTargetCode } from "@/api/system";

interface FormItemProps {
  id?: string;
  menu_key: string;
  menu_name: string;
  menu_type_code: MenuTypeCode;
  parent_id: string | null;
  path: string;
  component: string;
  route_redirect: string;
  route_meta: string;
  flex_form: Record<string, any>;
  icon: string;
  permission_key: string;
  is_external: boolean;
  external_url: string;
  open_target_code: OpenTargetCode;
  sort_no: number;
  is_visible: boolean;
  is_active: boolean;
  remark: string;
  /** 表单选项，不提交 */
  higherMenuOptions: Record<string, unknown>[];
  permissionOptions: Array<{ value: string; label: string }>;
}
interface FormProps {
  formInline: FormItemProps;
}

export type { FormItemProps, FormProps };
