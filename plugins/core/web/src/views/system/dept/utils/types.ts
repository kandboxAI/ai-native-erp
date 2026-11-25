interface DeptOption {
  id: string;
  department_name: string;
  disabled?: boolean;
  children?: DeptOption[];
}

interface OrgOption {
  id: string;
  org_name: string;
  org_type_code: string | null;
  school_id: string;
  school_name: string;
  is_active: boolean;
}

interface FormItemProps {
  id?: string;
  org_id: string;
  placement_label: string;
  department_no: string;
  department_name: string;
  parent_id: string | null;
  manager_user_id: string | null;
  sort_no: number | null;
  is_active: boolean;
  remark: string;
  higherDeptOptions: DeptOption[];
  managerOptions: Array<{ id: string; label: string }>;
}

interface FormProps {
  formInline: FormItemProps;
}

interface OrgFormItemProps {
  id?: string;
  org_no: string;
  org_name: string;
  org_type_code: string;
  parent_label: string;
  contact_name: string;
  contact_phone: string;
  province: string;
  city: string;
  district: string;
  address: string;
  sort_no: number | null;
  is_active: boolean;
  remark: string;
}

interface OrgFormProps {
  formInline: OrgFormItemProps;
}

type StructureKind = "org" | "department";

interface StructureRow {
  id: string;
  kind: StructureKind;
  name: string;
  code: string;
  type_code: string;
  type_label: string;
  is_active: boolean;
  sort_no: number | null;
  remark: string;
  org_id: string;
  parent_id: string | null;
  school_name: string;
  manager_user_id: string | null;
  manager_name: string;
  children?: StructureRow[];
}

export type {
  DeptOption,
  FormItemProps,
  FormProps,
  OrgFormItemProps,
  OrgFormProps,
  OrgOption,
  StructureKind,
  StructureRow
};
