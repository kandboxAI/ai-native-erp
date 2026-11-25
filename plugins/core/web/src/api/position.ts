import { http } from "@/utils/http";

export type Reply<T> = { code: number; message: string; data: T };
export type Position = {
  id: string;
  org_id: string;
  position_no: string;
  position_name: string;
  department_id: string;
  parent_position_id: string | null;
  is_department_head: boolean;
  headcount: number | null;
  sort_no: number | null;
  is_active: boolean;
  updated_at: string;
};
export type PositionOptions = {
  organizations: { id: string; name: string }[];
  departments: { id: string; org_id: string; name: string }[];
  positions: { id: string; org_id: string; name: string; is_active: boolean }[];
};
export const getPositionOptions = () =>
  http.request<Reply<PositionOptions>>("get", "/api/position/options");
export const listPositions = (params: {
  page: number;
  page_size: number;
  keyword: string;
}) =>
  http.request<Reply<{ items: Position[]; total: number }>>(
    "get",
    "/api/position/list",
    { params }
  );
// 树形展示读取完整岗位，避免同一部门被分页拆开；权限范围仍由列表接口过滤。
export async function fetchAllPositions(): Promise<Position[]> {
  const items: Position[] = [];
  for (let page = 1; ; page += 1) {
    const result = await listPositions({
      page,
      page_size: 100,
      keyword: ""
    });
    if (result.code !== 0) throw new Error(result.message);
    items.push(...(result.data.items as Position[]));
    if (!result.data.items.length || items.length >= result.data.total)
      return items;
  }
}

export const savePosition = (id: string | undefined, data: object) =>
  http.request<Reply<Position>>(
    id ? "put" : "post",
    `/api/position/${id ? `update/${id}` : "create"}`,
    { data }
  );

export const deletePosition = (id: string) =>
  http.request<Reply<boolean>>("delete", `/api/position/delete/${id}`);
