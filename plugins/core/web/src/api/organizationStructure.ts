/** /api/organization/list 列表项 */
export type OrganizationListRow = {
  id: string;
  org_no: string;
  org_name: string;
  org_type_code?: string | null;
  parent_id?: string | null;
  sort_no?: number | null;
  is_active?: boolean;
};

/** /api/organization/tree 节点 */
export type OrganizationTreeNode = {
  id: string;
  parent_id: string | null;
  org_no: string;
  org_name: string;
  org_type_code: string | null;
  sort_no: number | null;
  is_active: boolean;
  children: OrganizationTreeNode[];
};
