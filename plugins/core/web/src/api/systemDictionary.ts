import { http } from "@/utils/http";

export type ApiResponse<T> = {
  code: number;
  message: string;
  data: T;
};

export type PageResult<T> = {
  items: T[];
  total: number;
  page: number;
  page_size: number;
};

export type DictionaryTypeRow = {
  id: string;
  dict_code: string;
  dict_name: string;
  description: string | null;
  is_tenant_extensible: boolean;
  is_active: boolean;
  /** 平台内置字典，不可删除 */
  is_builtin: boolean;
  created_at: string;
  updated_at: string;
  updated_by: string | null;
};

/** 字典项平铺行（/api/dictionary/entry/list） */
export type SystemDictionaryRow = {
  id: string;
  dict_id: string;
  dict_code: string;
  dict_name: string;
  is_tenant_extensible: boolean;
  item_code: string;
  item_name: string;
  sort_no: number | null;
  is_builtin: boolean;
  is_active: boolean;
  remark: string | null;
  updated_at: string;
};

export type DictionaryListParams = {
  page?: number;
  page_size?: number;
  keyword?: string;
  is_active?: boolean;
  is_tenant_extensible?: boolean;
};

export type DictionaryEntryListParams = {
  page?: number;
  page_size?: number;
  keyword?: string;
  dict_id?: string;
  dict_code?: string;
  item_name?: string;
  is_active?: boolean;
};

export type DictionaryPayload = {
  dict_code: string;
  dict_name: string;
  description?: string | null;
  is_tenant_extensible?: boolean;
  is_active?: boolean;
};

/** 修改时 dict_code 不可改 */
export type DictionaryUpdatePayload = Partial<
  Omit<DictionaryPayload, "dict_code">
>;

export type DictionaryItemPayload = {
  dict_id: string;
  item_code: string;
  item_name: string;
  sort_no?: number | null;
  is_active?: boolean;
  remark?: string | null;
};

/** 内置项 item_code 不可改 */
export type DictionaryItemUpdatePayload = Partial<
  Omit<DictionaryItemPayload, "dict_id">
>;

/** 字典项表行（/api/dictionary_item/list） */
export type DictionaryItemRow = {
  id: string;
  dict_id: string;
  item_code: string;
  item_name: string;
  sort_no: number | null;
  is_builtin: boolean;
  is_active: boolean;
  remark: string | null;
  created_at: string;
  updated_at: string;
  updated_by?: string | null;
};

export type DictionaryItemListParams = {
  page?: number;
  page_size?: number;
  keyword?: string;
  dict_id?: string;
  is_active?: boolean;
  is_builtin?: boolean;
};

export type DictionaryOption = {
  item_code: string;
  item_name: string;
  sort_no: number | null;
  is_active: boolean;
};

export const listDictionaries = (params: DictionaryListParams) => {
  return http.request<ApiResponse<PageResult<DictionaryTypeRow>>>(
    "get",
    "/api/dictionary/list",
    { params }
  );
};

export const createDictionary = (data: DictionaryPayload) => {
  return http.request<ApiResponse<DictionaryTypeRow>>(
    "post",
    "/api/dictionary/create",
    { data }
  );
};

export const updateDictionary = (id: string, data: DictionaryUpdatePayload) => {
  return http.request<ApiResponse<DictionaryTypeRow>>(
    "put",
    `/api/dictionary/update/${id}`,
    { data }
  );
};

export const deleteDictionary = (id: string) => {
  return http.request<ApiResponse<{ deleted: boolean }>>(
    "delete",
    `/api/dictionary/delete/${id}`
  );
};

export const listDictionaryItems = (params: DictionaryItemListParams) => {
  return http.request<ApiResponse<PageResult<DictionaryItemRow>>>(
    "get",
    "/api/dictionary_item/list",
    { params }
  );
};

export const listDictionaryEntries = (params: DictionaryEntryListParams) => {
  return http.request<ApiResponse<PageResult<SystemDictionaryRow>>>(
    "get",
    "/api/dictionary/entry/list",
    { params }
  );
};

export const createDictionaryItem = (data: DictionaryItemPayload) => {
  return http.request<ApiResponse<unknown>>(
    "post",
    "/api/dictionary_item/create",
    { data }
  );
};

export const updateDictionaryItem = (
  id: string,
  data: DictionaryItemUpdatePayload
) => {
  return http.request<ApiResponse<unknown>>(
    "put",
    `/api/dictionary_item/update/${id}`,
    { data }
  );
};

export const deleteDictionaryItem = (id: string) => {
  return http.request<ApiResponse<{ deleted: boolean }>>(
    "delete",
    `/api/dictionary_item/delete/${id}`
  );
};

/** 下拉选项：{dict_code: [{item_code, item_name, ...}]}，登录用户均可读取 */
export const getDictionaryOptions = (
  dictCodes: string[],
  includeInactive = false
) => {
  return http.request<ApiResponse<Record<string, DictionaryOption[]>>>(
    "get",
    "/api/dictionary/options",
    {
      params: {
        dict_codes: dictCodes.join(","),
        include_inactive: includeInactive || undefined
      }
    }
  );
};
