import type { OrgAccessModeCode } from "@/api/systemUserProfile";

interface OrgDeptNode {
  id: string;
  name: string;
  /** org：组织；dept：部门 */
  node_type: "org" | "dept";
  org_id: string;
  disabled?: boolean;
  children?: OrgDeptNode[];
}

interface FormItemProps {
  id?: string;
  /** 用于判断是`新增`还是`修改` */
  title: string;
  email: string;
  mobile: string;
  password: string;
  full_name: string;
  display_name: string;
  org_id: string;
  org_access_mode_code: OrgAccessModeCode;
  org_ids: string[];
  department_id: string | null;
  role_ids: string[];
  position_ids: string[];
  is_active: boolean;
  /** 表单选项，不提交 */
  orgOptions: Array<{ id: string; org_name: string }>;
  deptTree: OrgDeptNode[];
  roleOptions: Array<{ id: string; role_name: string; role_no: string }>;
}
interface FormProps {
  formInline: FormItemProps;
}

interface RoleFormItemProps {
  display_name: string;
  /** 角色列表 */
  roleOptions: Array<{ id: string; role_name: string; role_no: string }>;
  /** 选中的角色 */
  ids: string[];
}
interface RoleFormProps {
  formInline: RoleFormItemProps;
}

export type {
  FormItemProps,
  FormProps,
  OrgDeptNode,
  RoleFormItemProps,
  RoleFormProps
};
