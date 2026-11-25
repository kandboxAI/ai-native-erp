import type { RoleDataScope } from "@/api/systemRole";

interface FormItemProps {
  /** 修改时使用 */
  id?: string;
  role_no: string;
  role_name: string;
  description: string;
  data_scope_code: RoleDataScope;
  is_active: boolean;
  /** 内置角色：编号不可改、不可停用；内置管理员数据范围不可改 */
  is_builtin: boolean;
}
interface FormProps {
  formInline: FormItemProps;
}

export type { FormItemProps, FormProps };
